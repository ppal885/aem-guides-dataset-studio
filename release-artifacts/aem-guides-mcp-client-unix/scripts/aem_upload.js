#!/usr/bin/env node

const fs = require('fs');

function loadConfigFromArgs(args) {
    if (args.length === 0) {
        throw new Error('Usage: node aem_upload.js --config-file <path>');
    }

    if (args[0] === '--config-file') {
        const configPath = args[1];
        if (!configPath) {
            throw new Error('Missing --config-file path');
        }
        return JSON.parse(fs.readFileSync(configPath, 'utf8').replace(/^\uFEFF/, ''));
    }

    return JSON.parse(args[0]);
}

async function uploadToAem(config) {
    const {
        FileSystemUploadOptions,
        FileSystemUpload
    } = require('@adobe/aem-upload');

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

    const hasBasicAuth = username && password;
    const hasBearerToken = accessToken && accessToken.trim().length > 0;
    if (!hasBasicAuth && !hasBearerToken) {
        throw new Error('Authentication required: provide username+password or accessToken');
    }

    const uploadUrl = `${aemBaseUrl.replace(/\/$/, '')}/${targetPath.replace(/^\//, '')}`;
    const authHeader = hasBearerToken
        ? `Bearer ${accessToken.trim()}`
        : `Basic ${Buffer.from(`${username}:${password}`).toString('base64')}`;

    const fsOptions = new FileSystemUploadOptions()
        .withDeepUpload(true)
        .withMaxUploadFiles(maxUploadFiles);

    fsOptions.options.url = uploadUrl;
    fsOptions.options.maxConcurrent = maxConcurrent;
    fsOptions.options.headers = {
        Authorization: authHeader
    };

    const fileUpload = new FileSystemUpload();
    const originalConsoleLog = console.log;
    const originalConsoleError = console.error;
    const originalConsoleWarn = console.warn;
    const originalConsoleInfo = console.info;

    console.log = (...args) => process.stderr.write(args.join(' ') + '\n');
    console.error = (...args) => process.stderr.write(args.join(' ') + '\n');
    console.warn = (...args) => process.stderr.write(args.join(' ') + '\n');
    console.info = (...args) => process.stderr.write(args.join(' ') + '\n');

    try {
        const startTime = Date.now();
        await fileUpload.upload(fsOptions, [sourcePath]);
        const duration = ((Date.now() - startTime) / 1000).toFixed(2);
        return {
            success: true,
            duration: parseFloat(duration),
            message: 'Upload completed successfully'
        };
    } catch (error) {
        return {
            success: false,
            error: error.message || String(error),
            message: 'Upload failed'
        };
    } finally {
        console.log = originalConsoleLog;
        console.error = originalConsoleError;
        console.warn = originalConsoleWarn;
        console.info = originalConsoleInfo;
    }
}

if (require.main === module) {
    try {
        const config = loadConfigFromArgs(process.argv.slice(2));
        uploadToAem(config)
            .then((result) => {
                console.log(JSON.stringify(result));
                process.exit(result.success ? 0 : 1);
            })
            .catch((error) => {
                console.log(JSON.stringify({
                    success: false,
                    error: error.message || String(error),
                    message: 'Upload failed'
                }));
                process.exit(1);
            });
    } catch (error) {
        console.log(JSON.stringify({
            success: false,
            error: error.message || String(error),
            message: 'Failed to parse configuration'
        }));
        process.exit(1);
    }
}

module.exports = { uploadToAem, loadConfigFromArgs };
