import { delay, createApiError, isRetryableError, type ApiError } from './utils';

export function getApiBase(): string {
  return process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
}

interface CircuitBreakerConfig {
  failureThreshold: number;
  recoveryTimeout: number;
  monitoringPeriod: number;
}

interface ApiClientConfig {
  baseUrl: string;
  timeout: number;
  uploadTimeout: number;
  maxRetries: number;
  circuitBreaker: CircuitBreakerConfig;
}

interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: ApiError;
}

class CircuitBreaker {
  private failureCount = 0;
  private lastFailureTime = 0;
  private state: 'closed' | 'open' | 'half-open' = 'closed';
  
  constructor(private config: CircuitBreakerConfig) {}
  
  async execute<T>(operation: () => Promise<T>): Promise<T> {
    if (this.state === 'open') {
      const now = Date.now();
      if (now - this.lastFailureTime > this.config.recoveryTimeout) {
        this.state = 'half-open';
      } else {
        throw createApiError('Circuit breaker is open', 'CIRCUIT_OPEN', 503);
      }
    }
    
    try {
      const result = await operation();
      if (this.state === 'half-open') {
        this.state = 'closed';
        this.failureCount = 0;
      }
      return result;
    } catch (error) {
      this.recordFailure();
      throw error;
    }
  }
  
  private recordFailure(): void {
    this.failureCount++;
    this.lastFailureTime = Date.now();
    
    if (this.failureCount >= this.config.failureThreshold) {
      this.state = 'open';
      console.warn(`Circuit breaker opened after ${this.failureCount} failures`);
    }
  }
  
  getState(): string {
    return this.state;
  }
}

class ApiClient {
  private config: ApiClientConfig;
  private circuitBreaker: CircuitBreaker;
  
  constructor(config?: Partial<ApiClientConfig>) {
    this.config = {
      baseUrl: getApiBase(),
      timeout: 30000, // 30 seconds default
      uploadTimeout: 120000, // 2 minutes for uploads
      maxRetries: 3,
      circuitBreaker: {
        failureThreshold: 5,
        recoveryTimeout: 60000, // 1 minute
        monitoringPeriod: 300000, // 5 minutes
      },
      ...config
    };
    
    this.circuitBreaker = new CircuitBreaker(this.config.circuitBreaker);
  }
  
  private async fetchWithTimeout(
    url: string,
    options: RequestInit,
    timeoutMs: number
  ): Promise<Response> {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
    
    try {
      const response = await fetch(url, {
        ...options,
        signal: controller.signal
      });
      return response;
    } finally {
      clearTimeout(timeoutId);
    }
  }
  
  private async executeWithRetry<T>(
    operation: () => Promise<T>,
    retryCount = 0
  ): Promise<T> {
    try {
      return await operation();
    } catch (error) {
      const apiError = this.normalizeError(error);
      
      if (retryCount < this.config.maxRetries && isRetryableError(apiError)) {
        // Exponential backoff with jitter
        const baseDelay = Math.min(1000 * Math.pow(2, retryCount), 10000);
        const jitter = Math.random() * 1000;
        await delay(baseDelay + jitter);
        
        console.log(`Retrying request (attempt ${retryCount + 1}/${this.config.maxRetries})`);
        return this.executeWithRetry(operation, retryCount + 1);
      }
      
      throw apiError;
    }
  }
  
  private normalizeError(error: any): ApiError {
    if (error.name === 'AbortError') {
      return createApiError('Request timeout', 'TIMEOUT', 408);
    }
    
    if (error instanceof Error) {
      return createApiError(
        error.message || 'Unknown error',
        'NETWORK_ERROR',
        0,
        { originalError: error }
      );
    }
    
    return createApiError('Unknown error', 'UNKNOWN', 0, { error });
  }
  
  private async request<T>(
    endpoint: string,
    options: RequestInit & { timeout?: number } = {}
  ): Promise<ApiResponse<T>> {
    const url = `${this.config.baseUrl}${endpoint}`;
    const timeout = options.timeout || this.config.timeout;
    
    try {
      const result = await this.circuitBreaker.execute(async () => {
        return await this.executeWithRetry(async () => {
          const response = await this.fetchWithTimeout(url, options, timeout);
          
          if (!response.ok) {
            let errorData: any = {};
            try {
              errorData = await response.json();
            } catch {
              // Ignore JSON parse errors
            }
            
            throw createApiError(
              errorData.detail || `Request failed: ${response.status}`,
              errorData.code || 'API_ERROR',
              response.status,
              errorData
            );
          }
          
          const data = await response.json();
          return data;
        });
      });
      
      return { success: true, data: result };
    } catch (error) {
      const apiError = error instanceof Error && 'status' in error
        ? error as ApiError
        : this.normalizeError(error);
      
      console.error('API request failed:', apiError);
      return { success: false, error: apiError };
    }
  }
  
  async presignUpload(
    filename: string,
    contentType: string,
    fileSize: number
  ): Promise<ApiResponse<any>> {
    // Validate file size client-side
    if (fileSize > 100 * 1024 * 1024) { // 100MB limit
      return {
        success: false,
        error: createApiError('File size exceeds 100MB limit', 'FILE_TOO_LARGE', 413)
      };
    }
    
    return this.request('/v1/uploads/presign', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        filename,
        content_type: contentType,
        file_size: fileSize
      }),
    });
  }
  
  async uploadToS3(
    url: string,
    fields: Record<string, string>,
    file: File,
    onProgress?: (progress: number) => void
  ): Promise<ApiResponse<void>> {
    try {
      // Calculate file hash for integrity check
      const fileHash = await this.calculateFileHash(file);
      
      const formData = new FormData();
      Object.entries(fields).forEach(([key, value]) => {
        formData.append(key, value);
      });
      formData.append('file', file);
      formData.append('x-amz-meta-file-hash', fileHash);
      
      // Use XMLHttpRequest for progress tracking
      const result = await new Promise<void>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        
        xhr.upload.addEventListener('progress', (event) => {
          if (event.lengthComputable && onProgress) {
            const progress = Math.round((event.loaded / event.total) * 100);
            onProgress(progress);
          }
        });
        
        xhr.addEventListener('load', () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            resolve();
          } else {
            reject(createApiError(
              `Upload failed: ${xhr.status}`,
              'UPLOAD_ERROR',
              xhr.status
            ));
          }
        });
        
        xhr.addEventListener('error', () => {
          reject(createApiError('Upload failed', 'NETWORK_ERROR', 0));
        });
        
        xhr.addEventListener('timeout', () => {
          reject(createApiError('Upload timeout', 'TIMEOUT', 408));
        });
        
        xhr.open('POST', url);
        xhr.timeout = this.config.uploadTimeout;
        xhr.send(formData);
      });
      
      return { success: true };
    } catch (error) {
      const apiError = this.normalizeError(error);
      return { success: false, error: apiError };
    }
  }
  
  async registerDocument(payload: {
    s3_key: string;
    original_filename: string;
    file_hash?: string;
  }): Promise<ApiResponse<any>> {
    return this.request('/v1/documents', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  }
  
  async getDocuments(
    limit = 10,
    offset = 0
  ): Promise<ApiResponse<any>> {
    return this.request(`/v1/documents?limit=${limit}&offset=${offset}`, {
      method: 'GET',
    });
  }
  
  async getDocument(documentId: string): Promise<ApiResponse<any>> {
    return this.request(`/v1/documents/${documentId}`, {
      method: 'GET',
    });
  }
  
  async searchDocuments(
    query: string,
    documentIds?: string[]
  ): Promise<ApiResponse<any>> {
    return this.request('/v1/qa/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query,
        document_ids: documentIds,
      }),
    });
  }
  
  async answerQuestion(
    question: string,
    documentIds?: string[]
  ): Promise<ApiResponse<any>> {
    return this.request('/v1/qa/answer', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question,
        document_ids: documentIds,
      }),
      timeout: 60000, // 1 minute for AI responses
    });
  }
  
  async getHealth(): Promise<ApiResponse<any>> {
    return this.request('/health', {
      method: 'GET',
      timeout: 5000, // Quick timeout for health checks
    });
  }
  
  private async calculateFileHash(file: File): Promise<string> {
    try {
      const buffer = await file.arrayBuffer();
      const hashBuffer = await crypto.subtle.digest('SHA-256', buffer);
      const hashArray = Array.from(new Uint8Array(hashBuffer));
      return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
    } catch (error) {
      console.warn('Failed to calculate file hash:', error);
      return '';
    }
  }
  
  getCircuitBreakerState(): string {
    return this.circuitBreaker.getState();
  }
}

// Export singleton instance
export const apiClient = new ApiClient();

// Export legacy functions for backward compatibility
export async function presignUpload(filename: string, contentType: string) {
  const file = { size: 0 } as File; // Legacy function doesn't have size
  const result = await apiClient.presignUpload(filename, contentType, file.size);
  if (!result.success) {
    throw new Error(result.error?.message || 'Presign failed');
  }
  return result.data;
}

export async function registerDocument(payload: { s3_key: string; original_filename: string }) {
  const result = await apiClient.registerDocument(payload);
  if (!result.success) {
    throw new Error(result.error?.message || 'Register failed');
  }
  return result.data;
}