#!/usr/bin/env node

const {
    FileSystemUploadOptions,
    FileSystemUpload,
    DirectBinaryUploadOptions
} = require('@adobe/aem-upload');

async function uploadToAem(config) {
    const {
        sourcePath,
        aemBaseUrl,
        targetPath,
        username,
        password,
        accessToken,
        maxConcurrent = 20,
        maxUploadFiles = 70000
    } = config;

    if (!sourcePath || !aemBaseUrl || !targetPath) {
        throw new Error('Missing required parameters: sourcePath, aemBaseUrl, targetPath');
    }

    // Require at least one auth method
    const hasBasicAuth = username && password;
    const hasBearerToken = accessToken && accessToken.trim().length > 0;

    if (!hasBasicAuth && !hasBearerToken) {
        throw new Error('Authentication required: provide username+password (Basic Auth) or accessToken (Bearer Token for AEM Cloud Service)');
    }

    const uploadUrl = `${aemBaseUrl.replace(/\/$/, '')}/${targetPath.replace(/^\//, '')}`;

    // Build auth header — Bearer token takes precedence (AEM Cloud Service)
    let authHeader;
    if (hasBearerToken) {
        authHeader = `Bearer ${accessToken.trim()}`;
    } else {
        const authToken = Buffer.from(`${username}:${password}`).toString('base64');
        authHeader = `Basic ${authToken}`;
    }

    // FileSystemUploadOptions handles filesystem-specific settings
    const fsOptions = new FileSystemUploadOptions()
        .withDeepUpload(true)
        .withMaxUploadFiles(maxUploadFiles);

    // Inject URL, auth, and concurrency directly into the options object
    // The upload() method reads these from fsOptions.options internally
    fsOptions.options.url = uploadUrl;
    fsOptions.options.maxConcurrent = maxConcurrent;
    fsOptions.options.headers = {
        'Authorization': authHeader
    };

    const fileUpload = new FileSystemUpload();
    
    // Redirect console output from the library to stderr so stdout stays clean for JSON
    const originalConsoleLog = console.log;
    const originalConsoleError = console.error;
    const originalConsoleWarn = console.warn;
    const originalConsoleInfo = console.info;
    
    // Redirect all console output to stderr
    console.log = (...args) => {
        process.stderr.write(args.join(' ') + '\n');
    };
    console.error = (...args) => {
        process.stderr.write(args.join(' ') + '\n');
    };
    console.warn = (...args) => {
        process.stderr.write(args.join(' ') + '\n');
    };
    console.info = (...args) => {
        process.stderr.write(args.join(' ') + '\n');
    };
    
    try {
        const startTime = Date.now();
        await fileUpload.upload(fsOptions, [sourcePath]);
        const duration = ((Date.now() - startTime) / 1000).toFixed(2);
        
        // Restore console
        console.log = originalConsoleLog;
        console.error = originalConsoleError;
        console.warn = originalConsoleWarn;
        console.info = originalConsoleInfo;
        
        return {
            success: true,
            duration: parseFloat(duration),
            message: 'Upload completed successfully'
        };
    } catch (error) {
        // Restore console
        console.log = originalConsoleLog;
        console.error = originalConsoleError;
        console.warn = originalConsoleWarn;
        console.info = originalConsoleInfo;
        
        return {
            success: false,
            error: error.message || String(error),
            message: 'Upload failed'
        };
    }
}

if (require.main === module) {
    const args = process.argv.slice(2);
    
    if (args.length === 0) {
        console.error('Usage: node aem_upload.js <config_json>');
        process.exit(1);
    }

    try {
        const config = JSON.parse(args[0]);
        uploadToAem(config)
            .then(result => {
                console.log(JSON.stringify(result));
                process.exit(result.success ? 0 : 1);
            })
            .catch(error => {
                const errorResult = JSON.stringify({
                    success: false,
                    error: error.message || String(error),
                    message: 'Upload failed'
                });
                console.log(errorResult);
                process.exit(1);
            });
    } catch (error) {
        const errorResult = JSON.stringify({
            success: false,
            error: error.message || String(error),
            message: 'Failed to parse configuration'
        });
        console.log(errorResult);
        process.exit(1);
    }
}

module.exports = { uploadToAem };
