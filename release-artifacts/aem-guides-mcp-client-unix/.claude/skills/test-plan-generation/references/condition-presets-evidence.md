# Condition presets: behaviour and UI evidence

Source: [Use condition presets](https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/conditional-content/generate-output-use-condition-presets), updated May 15, 2026; ingested and visually inspected September 9, 2026.
Documentation evidence only: not Human approval, a product-test result, or automatic AC scope.

## Retrieve the relevant behaviour

Actual local chunk prefix: `aem_ingest_c50c5d5527_`. Prefer the exact source URL
when IDs differ. Select only facts applicable to the current map, surface and build.

| Suffix | Evidence to investigate |
| --- | --- |
| `_0`–`_2` | Condition presets control conditional output. Console creation requires a unique name; empty, invalid-character and duplicate names error. Hyphen and underscore are allowed separators; no complete character whitelist is supplied. |
| `_2`–`_3` | Attributes panel draws attributes from map references; the right panel lists conditions added to the preset. Select whole attributes, individual values, attribute/value pairs by drag, or all values. Add transfers selections; Remove removes selected entries. |
| `_3`–`_4` | Console attributes default to Include. Include, Exclude, Passthrough and Flag can be applied per row or to selected rows. Unsaved switching/closing warns. Created presets are offered by Output presets. |
| `_5` | Console Options opens Rename, Duplicate and Delete condition preset dialogs; deletion requires confirmation. |
| `_6`–`_7` | Dashboard Name Condition and Set default action to controls; the default includes attributes not added to the preset. Selected-attribute and individual overrides are supported. |
| `_8`–`_9` | Dashboard-section copy, editing and multi-delete workflow; retain the naming ambiguity below. |

## Do not collapse these surface differences

| Context | Documented rule |
| --- | --- |
| Map console | Added attributes default to Include; duplicate name is `<selected condition preset name>_1`, editable. |
| Map dashboard section | Set default action to applies to all attributes, including unlisted ones; duplicate name is `<selected condition preset name>_Duplicate`, editable. |

The dashboard section's edit/copy/delete steps nevertheless say **DITA map console**.
That is an unresolved source naming inconsistency, not proof of identical interfaces.
Retrieve the section context and inspect the target UI before asserting either workflow.
The example attribute counts and operating-system values are illustrative, not limits.

## Every image inspected

The raw article contains one image; it was saved and opened, with no sampling:
[Condition presets workspace image](https://experienceleague.adobe.com/en/docs/experience-manager-guides/using/user-guide/map-management-publishing/output-gen/conditional-content/media_158cdce9a299c06fcc004975578f1067199036c51.png).

It shows Map console with Condition presets selected, a searchable preset list and
`sample-preset_1` open. The middle **Attributes** column contains a selectable
`platform` group and `Mac` value. The right table has **Attribute Name**, **Value**,
and **Action** columns; the selected `platform` / `Window` row uses Include.
The toolbar shows Include, Exclude, Flag, Passthrough and Remove. Save is visible;
Add is greyed out. These example values and enabled states are not universal defaults.
The image does not show dialogs, dropdown contents, dashboard controls or generated output.

## Terminology and limits

The documented **Condition presets panel** is not the existing authoring **Conditions
panel**. Reuse **Map console**, **Map dashboard**, **Condition Presets** and **Output
Presets**; preserve **Attributes panel** (prose) versus **Attributes** (screenshot).
Documented dialog and dashboard-control names have `DOCUMENT_VERIFIED` provenance
in `guides_vocabulary.json`. No new Human-approved blocking rules are implied.

Do not infer exact error/warning text, a suffix-collision sequence, Flag styling,
DITAVAL-file precedence, output-engine parity or persistence after upgrades from
this page. Retrieve separate evidence when these questions are material. Keep
condition-preset editing distinct from output-preset selection and the DITAVAL editor.
