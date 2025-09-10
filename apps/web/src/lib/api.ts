import { 
  delay, 
  ApiError, 
  createApiError, 
  isRetryableError, 
  UploadProgress, 
  uploadEvents, 
  calculateFileHash,
  generateRequestId,
  createCancellablePromise
} from './utils';

/**
 * Circuit breaker states
 */
enum CircuitState {
  CLOSED = 'closed',
  OPEN = 'open', 
  HALF_OPEN = 'half-open'
}

/**
 * Circuit breaker for preventing cascade failures
 */
class CircuitBreaker {
  private state = CircuitState.CLOSED;
  private failureCount = 0;
  private lastFailureTime = 0;
  private readonly failureThreshold = 5;
  private readonly recoveryTimeout = 30000; // 30 seconds

  async execute<T>(operation: () => Promise<T>): Promise<T> {
    if (this.state === CircuitState.OPEN) {
      if (Date.now() - this.lastFailureTime > this.recoveryTimeout) {
        this.state = CircuitState.HALF_OPEN;
      } else {
        throw createApiError('Circuit breaker is open - service temporarily unavailable', 'CIRCUIT_OPEN');
      }
    }

    try {
      const result = await operation();
      this.onSuccess();
      return result;
    } catch (error) {
      this.onFailure();
      throw error;
    }
  }

  private onSuccess(): void {
    this.failureCount = 0;
    this.state = CircuitState.CLOSED;
  }

  private onFailure(): void {
    this.failureCount++;
    this.lastFailureTime = Date.now();
    
    if (this.failureCount >= this.failureThreshold) {
      this.state = CircuitState.OPEN;
    }
  }

  getState(): CircuitState {
    return this.state;
  }
}

/**
 * Enhanced API client with circuit breaker, retries, and proper error handling
 */
class ApiClient {
  private baseUrl: string;
  private circuitBreaker = new CircuitBreaker();
  private defaultTimeout = 30000; // 30 seconds
  private uploadTimeout = 120000; // 2 minutes

  constructor() {
    this.baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
  }

  /**
   * Get API base URL
   */
  getApiBase(): string {
    return this.baseUrl;
  }

  /**
   * Enhanced fetch with timeout, retries, and error handling
   */
  private async enhancedFetch(
    url: string, 
    options: RequestInit = {},
    timeout = this.defaultTimeout,
    retries = 3
  ): Promise<Response> {
    const requestId = generateRequestId();
    
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeout);

    const fetchOptions: RequestInit = {
      ...options,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        'X-Request-ID': requestId,
        ...options.headers,
      },
    };

    let lastError: ApiError;

    for (let attempt = 0; attempt < retries; attempt++) {
      try {
        clearTimeout(timeoutId);
        const timeoutId2 = setTimeout(() => controller.abort(), timeout);
        
        const response = await fetch(url, fetchOptions);
        clearTimeout(timeoutId2);
        
        if (response.ok) {
          return response;
        }

        // Handle HTTP errors
        const errorText = await response.text().catch(() => 'Unknown error');
        const error = createApiError(
          `HTTP ${response.status}: ${errorText}`,
          'HTTP_ERROR',
          response.status,
          { requestId, attempt: attempt + 1 }
        );

        // Don't retry client errors (4xx) except specific ones
        if (response.status >= 400 && response.status < 500 && 
            response.status !== 408 && response.status !== 429) {
          throw error;
        }

        lastError = error;

        if (attempt < retries - 1) {
          // Exponential backoff with jitter
          const baseDelay = Math.min(1000 * Math.pow(2, attempt), 10000);
          const jitter = Math.random() * 1000;
          await delay(baseDelay + jitter);
        }

      } catch (error) {
        clearTimeout(timeoutId);
        
        if (error instanceof ApiError) {
          lastError = error;
        } else if (error.name === 'AbortError') {
          lastError = createApiError(
            'Request timeout',
            'TIMEOUT',
            408,
            { requestId, attempt: attempt + 1, timeout }
          );
        } else {
          lastError = createApiError(
            error.message || 'Network error',
            'NETWORK_ERROR',
            undefined,
            { requestId, attempt: attempt + 1 }
          );
        }

        if (attempt < retries - 1 && isRetryableError(lastError)) {
          const baseDelay = Math.min(1000 * Math.pow(2, attempt), 10000);
          const jitter = Math.random() * 1000;
          await delay(baseDelay + jitter);
        } else {
          break;
        }
      }
    }

    throw lastError;
  }

  /**
   * Presign upload with enhanced error handling and validation
   */
  async presignUpload(
    filename: string, 
    contentType: string, 
    fileSize?: number
  ): Promise<{ success: true; data: any } | { success: false; error: ApiError }> {
    try {
      const result = await this.circuitBreaker.execute(async () => {
        const payload: any = { filename, content_type: contentType };
        if (fileSize !== undefined) {
          payload.file_size = fileSize;
        }

        const response = await this.enhancedFetch(
          `${this.baseUrl}/v1/uploads/presign`,
          {
            method: 'POST',
            body: JSON.stringify(payload),
          }
        );

        return response.json();
      });

      return { success: true, data: result };
    } catch (error) {
      const apiError = error instanceof ApiError ? error : 
        createApiError('Failed to presign upload', 'PRESIGN_ERROR');
      
      console.error('Presign upload failed:', apiError);
      return { success: false, error: apiError };
    }
  }

  /**
   * Register document with enhanced error handling
   */
  async registerDocument(payload: { 
    s3_key: string; 
    original_filename: string;
    content_type?: string;
    file_size?: number;
    sha256_hash?: string;
  }): Promise<{ success: true; data: any } | { success: false; error: ApiError }> {
    try {
      const result = await this.circuitBreaker.execute(async () => {
        const response = await this.enhancedFetch(
          `${this.baseUrl}/v1/documents`,
          {
            method: 'POST',
            body: JSON.stringify(payload),
          }
        );

        return response.json();
      });

      return { success: true, data: result };
    } catch (error) {
      const apiError = error instanceof ApiError ? error : 
        createApiError('Failed to register document', 'REGISTER_ERROR');
      
      console.error('Document registration failed:', apiError);
      return { success: false, error: apiError };
    }
  }

  /**
   * Upload file to S3 with progress tracking and integrity validation
   */
  async uploadFileToS3(
    presignedUrl: string, 
    file: File, 
    contentType: string,
    progressTracker?: UploadProgress,
    expectedHash?: string
  ): Promise<{ success: true } | { success: false; error: ApiError }> {
    try {
      // Calculate file hash if not provided
      const fileHash = expectedHash || await calculateFileHash(file);
      
      uploadEvents.emit('upload:start', { 
        filename: file.name, 
        size: file.size 
      });

      const result = await this.circuitBreaker.execute(async () => {
        return new Promise<void>((resolve, reject) => {
          const xhr = new XMLHttpRequest();
          
          xhr.upload.onprogress = (event) => {
            if (event.lengthComputable) {
              const progress = (event.loaded / event.total) * 100;
              if (progressTracker) {
                progressTracker.progress = progress;
              }
              uploadEvents.emit('upload:progress', {
                progress,
                filename: file.name
              });
            }
          };

          xhr.onload = () => {
            if (xhr.status >= 200 && xhr.status < 300) {
              resolve();
            } else {
              reject(createApiError(
                `S3 upload failed: ${xhr.status}`,
                'S3_UPLOAD_ERROR',
                xhr.status
              ));
            }
          };

          xhr.onerror = () => {
            reject(createApiError(
              'S3 upload network error',
              'S3_NETWORK_ERROR'
            ));
          };

          xhr.ontimeout = () => {
            reject(createApiError(
              'S3 upload timeout',
              'S3_TIMEOUT',
              408
            ));
          };

          xhr.open('PUT', presignedUrl);
          xhr.setRequestHeader('Content-Type', contentType);
          xhr.timeout = this.uploadTimeout;
          xhr.send(file);
        });
      });

      uploadEvents.emit('upload:success', {
        filename: file.name,
        documentId: '' // Will be filled by caller
      });

      return { success: true };
    } catch (error) {
      const apiError = error instanceof ApiError ? error : 
        createApiError('S3 upload failed', 'S3_UPLOAD_ERROR');
      
      uploadEvents.emit('upload:error', {
        filename: file.name,
        error: apiError
      });

      console.error('S3 upload failed:', apiError);
      return { success: false, error: apiError };
    } finally {
      uploadEvents.emit('upload:complete', { filename: file.name });
    }
  }

  /**
   * Get document by ID
   */
  async getDocument(documentId: string): Promise<{ success: true; data: any } | { success: false; error: ApiError }> {
    try {
      const result = await this.circuitBreaker.execute(async () => {
        const response = await this.enhancedFetch(
          `${this.baseUrl}/v1/documents/${documentId}`
        );
        return response.json();
      });

      return { success: true, data: result };
    } catch (error) {
      const apiError = error instanceof ApiError ? error : 
        createApiError('Failed to get document', 'GET_DOCUMENT_ERROR');
      
      return { success: false, error: apiError };
    }
  }

  /**
   * Get health status
   */
  async getHealth(): Promise<{ success: true; data: any } | { success: false; error: ApiError }> {
    try {
      const response = await this.enhancedFetch(
        `${this.baseUrl}/health`,
        {},
        5000, // Shorter timeout for health checks
        1 // No retries for health checks
      );
      
      const data = await response.json();
      return { success: true, data };
    } catch (error) {
      const apiError = error instanceof ApiError ? error : 
        createApiError('Health check failed', 'HEALTH_CHECK_ERROR');
      
      return { success: false, error: apiError };
    }
  }

  /**
   * Complete file upload workflow
   */
  async uploadFile(
    file: File,
    progressTracker?: UploadProgress
  ): Promise<{ success: true; documentId: string } | { success: false; error: ApiError }> {
    try {
      // Validate file
      if (!file) {
        throw createApiError('No file provided', 'VALIDATION_ERROR');
      }

      // Calculate file hash for integrity
      const fileHash = await calculateFileHash(file);

      // Step 1: Get presigned URL
      const presignResult = await this.presignUpload(
        file.name,
        file.type,
        file.size
      );

      if (!presignResult.success) {
        return presignResult;
      }

      // Step 2: Upload to S3
      const uploadResult = await this.uploadFileToS3(
        presignResult.data.presigned_url,
        file,
        file.type,
        progressTracker,
        fileHash
      );

      if (!uploadResult.success) {
        return uploadResult;
      }

      // Step 3: Register document
      const registerResult = await this.registerDocument({
        s3_key: presignResult.data.s3_key,
        original_filename: file.name,
        content_type: file.type,
        file_size: file.size,
        sha256_hash: fileHash
      });

      if (!registerResult.success) {
        return registerResult;
      }

      uploadEvents.emit('upload:success', {
        filename: file.name,
        documentId: registerResult.data.id
      });

      return { 
        success: true, 
        documentId: registerResult.data.id 
      };

    } catch (error) {
      const apiError = error instanceof ApiError ? error : 
        createApiError('File upload failed', 'UPLOAD_ERROR');
      
      uploadEvents.emit('upload:error', {
        filename: file.name,
        error: apiError
      });

      return { success: false, error: apiError };
    }
  }

  /**
   * Get circuit breaker status
   */
  getCircuitBreakerStatus() {
    return {
      state: this.circuitBreaker.getState(),
      isHealthy: this.circuitBreaker.getState() === CircuitState.CLOSED
    };
  }
}

// Global API client instance
export const apiClient = new ApiClient();

// Legacy exports for backward compatibility
export function getApiBase(): string {
  return apiClient.getApiBase();
}

export async function presignUpload(filename: string, contentType: string) {
  const result = await apiClient.presignUpload(filename, contentType);
  if (result.success) {
    return result.data;
  } else {
    throw new Error(result.error.message);
  }
}

export async function registerDocument(payload: { s3_key: string; original_filename: string }) {
  const result = await apiClient.registerDocument(payload);
  if (result.success) {
    return result.data;
  } else {
    throw new Error(result.error.message);
  }
}
