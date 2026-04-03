# Root Cause Analysis: Asset Update API Returning 500

## Problem Statement

`POST /bin/guides/v1/asset/update` returns **HTTP 500** when saving DITA content from the XML Editor.

**Observed:**
- Response: `content-type: text/html` (~1033 bytes)
- Request: Multipart form with gzip-compressed file, `path`, `resourceType`
- Asset path: `/content/dam/________000000/GUID-b4711993-f9b9-40d4-b520-a2d8646a76e7.dita`
- Autosave enabled (same endpoint called periodically)
- **Occurs specifically for GUID file names** (e.g. `GUID-xxx.dita`), not for regular filenames
- **Unique file names** (`xmleditor.uniquefilenames`) enabled for XML Editor → new assets use GUID-style names

## Call Flow

```
saveAll → saveFile → checkOutStatus → saveXml → validate → saveAssetGzip
                                                              ↓
                                    POST /bin/guides/v1/asset/update → 500
```

**Code path:**
```
AssetServlet.updateAsset()
  → AssetServiceImpl.updateAsset()
    → validateRequestObject(), checkIfAssetIsValid(), checkAndUnlockAsset()
    → saveUpdatedData() → GuidesResource.processAndWriteStreamWithoutLock()
      → DitaResource.writeAndProcessDitaResourceDoc() [for .dita]
```

---

## Honest Assessment

**Without the actual exception and stack trace from AEM `error.log`, the root cause cannot be definitively identified.** The analysis below is based on code inspection and likely failure points.

---

## Key Finding: HTML vs JSON

Our servlet (`GuidesServletBase` → `AssetServlet`) **always** returns JSON on errors:

- `response.setContentType(JSON_CONTENT_TYPE)` is set at the start
- `catch (Throwable e)` writes `apiError.toString()` (JSON) for any uncaught exception
- `AssetServlet.updateAsset` catches `ApplicationException` and `RuntimeException` and returns JSON 500

**Therefore, a `content-type: text/html` 500 strongly suggests the failure occurs outside our servlet’s error handling**, such as:

1. **Before our code runs** – Sling/AEM multipart parsing, request size limits, or filters
2. **In a different layer** – CDN/proxy (`x-served-by: cache-del-vibw2260031-DEL` in HAR) serving a cached HTML error page
3. **Framework error handler** – AEM’s default error handler returning HTML when something fails before our catch blocks

---

## Code Review: What Is Already Handled

| Area | Status |
|------|--------|
| **Null encoding** | `StreamsRequestBaseDto.getUnzippedInputStream()` uses `encoding == null \|\| !encoding.equals("application/gzip")` – null-safe |
| **RuntimeException** | `AssetServlet.updateAsset` catches `RuntimeException` and returns JSON 500 |
| **ApplicationException** | Same – caught and returned as JSON 500 |
| **GuidesServletBase** | `catch (Throwable)` returns JSON for any uncaught exception |

---

## Possible Causes (Unconfirmed)

### 1. Multipart / Request Parsing (High)

- Sling fails to parse the multipart request (malformed boundary, size limit, timeout)
- `request.getRequestParameterMap()` may throw before our `parseMultipartContent` completes
- Such failures can be handled by Sling/AEM with an HTML error page

**Check:** AEM `error.log` for `IOException`, `IllegalStateException`, or Sling multipart errors at request time.

### 2. Request Size Limit (Medium)

- Default Sling/AEM limits on request body size
- Large gzip payload could be rejected before parsing

**Check:** `org.apache.sling.engine` / request size configuration; logs for size-related errors.

### 3. GZIP Decompression (Medium)

- `StreamsRequestBaseDto.getUnzippedInputStream()` loads the full decompressed content into memory
- Corrupted or non-gzip data → `GZIPInputStream` throws `IOException` → wrapped as `RuntimeException`
- Very large files → possible `OutOfMemoryError`

Our handlers would normally convert these to JSON 500. If the failure happens in a way that bypasses our handlers (e.g. during async processing or in a different thread), HTML could still be returned.

### 4. CDN / Proxy (Medium)

- HAR shows `x-served-by: cache-del-vibw2260031-DEL` (likely CDN)
- Origin 500 might be replaced by a cached HTML error page

**Check:** Whether the HTML 500 comes from the CDN or directly from AEM.

### 5. DitaResource Processing (Lower)

- `DitaResource.writeAndProcessDitaResourceDoc()` does XML parsing, COR chain, JCR writes
- Can throw `ApplicationException` (wraps `RepositoryException`, `SAXException`)

These are caught by our servlet and returned as JSON 500, so they are unlikely to explain an HTML response unless the failure occurs in an unexpected context.

### 6. GUID File Names – Different Code Path (High, given user report)

For paths like `/content/dam/.../GUID-xxx.dita`, `ReferenceFactory.getReference()` returns **UuidReference** (not PathReference) because the filename matches the GUID regex. This triggers a different resolution path:

- **PathReference**: Resolves node directly by path via `p.getNode(session)`.
- **UuidReference**: Resolves via `UuidUtils.lookupByUUID()` or a path-based “hack” that requires `UuidUtils.checkIfPostProcessAfterCreateInSync(node)` to be true.

**In `UuidReference.getNode()`** (`core/utils/.../UuidReference.java`):

1. **Path-based path** (lines 100–111): When `source` matches the path and the node exists, it checks `checkIfPostProcessAfterCreateInSync(node)`. If the node is **not postprocessed** (e.g. missing or out-of-sync `guides:assetState` / `guides:lastProcessed`), it **returns null**.
2. **UUID lookup path** (lines 114–126): If the UUID is not found in the reference store, or the node is not postprocessed, it **returns null**.
3. **Exception path** (lines 145–148): Any exception is caught and **returns null**.

When `getNode()` returns null, `ResourceFactory.visit(UuidReference)` throws `ApplicationException`, and `saveUpdatedData` throws `ApplicationException("Unable to fetch resource with path " + path)`. That should still be handled as JSON 500 by our servlet.

**Check:** For failing GUID assets, verify in CRXDE that `jcr:content` has `guides:assetState` and `guides:lastProcessed` set and consistent. If the asset is not yet postprocessed or is out of sync, `UuidReference.getNode()` will return null and the update will fail.

---

## Recommended Actions

### 1. Get the Real Exception (Critical)

At the time of the 500, inspect:

- `crx-quickstart/logs/error.log` – full stack trace
- Any Sling/servlet logs
- Whether the error occurs before `AssetServlet.updateAsset` is invoked

### 2. Reproduce with Logging

- Enable DEBUG for `com.adobe.guides.assets.servlet.AssetServlet`
- Confirm whether the request reaches `updateAsset` and where it fails

### 3. Verify Request Format

- `file`: gzip blob with `Content-Type: application/gzip`
- `path`: full asset path
- `resourceType`: `GUIDES_RESOURCE`
- Asset exists and the user has write permission

### 4. Autosave

- With autosave on, the update endpoint is called periodically
- Temporarily disable autosave to see if the 500 occurs only on autosave or also on manual save

### 5. Bypass CDN (If Applicable)

- Hit AEM directly (e.g. `localhost:4502` or internal host) to see if the HTML 500 is from AEM or from the CDN

### 6. GUID-Specific: Verify Post-Process State

- In CRXDE, open the failing asset (e.g. `/content/dam/________000000/GUID-xxx.dita`)
- Check `jcr:content` for `guides:assetState` and `guides:lastProcessed`
- If missing or inconsistent, `UuidReference.getNode()` returns null → update fails
- Compare with a working non-GUID asset to see the expected property values

---

## Summary

| Finding | Notes |
|---------|-------|
| HTML 500 | Suggests failure outside our servlet’s JSON error handling |
| GUID-only | Different code path via `UuidReference`; `getNode()` can return null if asset not postprocessed |
| Defensive code | Null checks and exception handlers are in place |
| Root cause | Cannot be confirmed without `error.log` and stack trace |
| Next step | Capture exception at 500 time; for GUID files, verify `guides:assetState` / `guides:lastProcessed` |
