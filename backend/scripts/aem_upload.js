#!/usr/bin/env node

const {
    FileSystemUploadOptions,
    FileSystemUpload
} = require('@adobe/aem-upload');

const {RegularExpressions} = require("@adobe/aem-upload/dist/constants");

async function uploadToAem(config) {
    const {
        sourcePath,
        aemBaseUrl,
        targetPath,
        username,
        password,
        maxConcurrent = 20,
        maxUploadFiles = 70000
    } = config;

    if (!sourcePath || !aemBaseUrl || !targetPath || !username || !password) {
        throw new Error('Missing required parameters: sourcePath, aemBaseUrl, targetPath, username, password');
    }

    const uploadUrl = `${aemBaseUrl.replace(/\/$/, '')}/${targetPath.replace(/^\//, '')}`;

    const options = new FileSystemUploadOptions()
        .withUrl(uploadUrl)
        .withDeepUpload(true)
        .withMaxUploadFiles(maxUploadFiles)
        .withMaxConcurrent(maxConcurrent)
        .withBasicAuth(`${username}:${password}`)
        .withFolderNodeNameProcessor(async (folderName) => {
            return folderName.replace(RegularExpressions.INVALID_FOLDER_CHARACTERS_REGEX, '-');
        });

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
        await fileUpload.upload(options, [sourcePath]);
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
