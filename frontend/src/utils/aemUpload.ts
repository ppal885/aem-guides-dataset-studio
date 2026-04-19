export interface AemUploadConfig {
  aem_base_url: string;
  target_path: string;
  username?: string;
  password?: string;
  access_token?: string;
  max_concurrent?: number;
  max_upload_files?: number;
}

export interface AemUploadResponse {
  success: boolean;
  job_id: string;
  message: string;
  duration?: number;
}

export interface AemUploadError {
  detail: string;
}

export async function uploadDatasetToAem(
  jobId: string,
  config: AemUploadConfig
): Promise<AemUploadResponse> {
  const response = await fetch(`/api/v1/datasets/${jobId}/upload-to-aem`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(config),
  });

  if (!response.ok) {
    let errorMessage = 'Upload failed';
    try {
      const error: AemUploadError = await response.json();
      errorMessage = error.detail || errorMessage;
    } catch {
      const errorText = await response.text().catch(() => 'Unknown error');
      errorMessage = errorText || errorMessage;
    }
    throw new Error(errorMessage);
  }

  return response.json();
}
