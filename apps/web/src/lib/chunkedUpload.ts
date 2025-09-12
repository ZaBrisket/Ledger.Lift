/**
 * Chunked upload utility using Resumable.js for reliable file uploads.
 */
import Resumable from 'resumablejs';

export interface ChunkedUploadOptions {
  chunkSize?: number;
  simultaneousUploads?: number;
  testChunks?: boolean;
  throttleProgressCallbacks?: number;
  maxChunkRetries?: number;
  chunkRetryInterval?: number;
}

export interface UploadProgress {
  progress: number;
  filename: string;
  bytesUploaded: number;
  totalBytes: number;
  chunksUploaded: number;
  totalChunks: number;
}

export interface UploadResult {
  success: boolean;
  documentId?: string;
  error?: string;
  filename: string;
}

export class ChunkedUploader {
  private resumable: Resumable;
  private options: Required<ChunkedUploadOptions>;
  private uploadPromise: Promise<UploadResult> | null = null;
  private uploadResolve: ((result: UploadResult) => void) | null = null;
  private uploadReject: ((error: Error) => void) | null = null;
  private progressCallback?: (progress: UploadProgress) => void;

  constructor(
    private apiBase: string,
    options: ChunkedUploadOptions = {}
  ) {
    this.options = {
      chunkSize: 5 * 1024 * 1024, // 5MB chunks
      simultaneousUploads: 3,
      testChunks: true,
      throttleProgressCallbacks: 500,
      maxChunkRetries: 3,
      chunkRetryInterval: 1000,
      ...options
    };

    this.resumable = new Resumable({
      target: `${apiBase}/v1/uploads/chunks`,
      chunkSize: this.options.chunkSize,
      simultaneousUploads: this.options.simultaneousUploads,
      testChunks: this.options.testChunks,
      throttleProgressCallbacks: this.options.throttleProgressCallbacks,
      maxChunkRetries: this.options.maxChunkRetries,
      chunkRetryInterval: this.options.chunkRetryInterval,
      headers: {
        'X-Request-ID': this.generateRequestId()
      }
    });

    this.setupEventHandlers();
  }

  private setupEventHandlers(): void {
    this.resumable.on('fileAdded', (file: Resumable.ResumableFile) => {
      console.log('File added:', file.fileName);
    });

    this.resumable.on('fileProgress', (file: Resumable.ResumableFile) => {
      const progress = file.progress(false) * 100;
      const bytesUploaded = file.size * file.progress(false);
      const totalBytes = file.size;
      const chunksUploaded = file.chunks.length;
      const totalChunks = Math.ceil(file.size / this.options.chunkSize);

      if (this.progressCallback) {
        this.progressCallback({
          progress,
          filename: file.fileName,
          bytesUploaded,
          totalBytes,
          chunksUploaded,
          totalChunks
        });
      }
    });

    this.resumable.on('fileSuccess', (file: Resumable.ResumableFile, message: string) => {
      try {
        const response = JSON.parse(message);
        if (this.uploadResolve) {
          this.uploadResolve({
            success: true,
            documentId: response.document_id,
            filename: file.fileName
          });
        }
      } catch (error) {
        console.error('Failed to parse upload response:', error);
        if (this.uploadReject) {
          this.uploadReject(new Error('Invalid server response'));
        }
      }
    });

    this.resumable.on('fileError', (file: Resumable.ResumableFile, message: string) => {
      console.error('Upload error:', message);
      if (this.uploadReject) {
        this.uploadReject(new Error(`Upload failed: ${message}`));
      }
    });

    this.resumable.on('error', (message: string, file: Resumable.ResumableFile) => {
      console.error('Resumable error:', message);
      if (this.uploadReject) {
        this.uploadReject(new Error(`Upload error: ${message}`));
      }
    });

    this.resumable.on('uploadStart', () => {
      console.log('Upload started');
    });

    this.resumable.on('complete', () => {
      console.log('Upload completed');
    });

    this.resumable.on('pause', () => {
      console.log('Upload paused');
    });

    this.resumable.on('cancel', () => {
      console.log('Upload cancelled');
      if (this.uploadReject) {
        this.uploadReject(new Error('Upload cancelled'));
      }
    });
  }

  private generateRequestId(): string {
    return `req_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  /**
   * Upload a file with chunked upload support.
   */
  async uploadFile(
    file: File,
    progressCallback?: (progress: UploadProgress) => void
  ): Promise<UploadResult> {
    // Cancel any existing upload
    if (this.uploadPromise) {
      this.cancel();
    }

    this.progressCallback = progressCallback;

    // Create new promise for this upload
    this.uploadPromise = new Promise<UploadResult>((resolve, reject) => {
      this.uploadResolve = resolve;
      this.uploadReject = reject;
    });

    try {
      // Add file to resumable
      this.resumable.addFile(file);

      // Start upload
      this.resumable.upload();

      // Wait for completion
      const result = await this.uploadPromise;
      return result;

    } catch (error) {
      throw error;
    } finally {
      // Clean up
      this.uploadPromise = null;
      this.uploadResolve = null;
      this.uploadReject = null;
      this.progressCallback = undefined;
    }
  }

  /**
   * Pause the current upload.
   */
  pause(): void {
    this.resumable.pause();
  }

  /**
   * Resume the current upload.
   */
  resume(): void {
    this.resumable.upload();
  }

  /**
   * Cancel the current upload.
   */
  cancel(): void {
    this.resumable.cancel();
    if (this.uploadReject) {
      this.uploadReject(new Error('Upload cancelled'));
    }
  }

  /**
   * Check if upload is in progress.
   */
  isUploading(): boolean {
    return this.resumable.isUploading();
  }

  /**
   * Get current progress.
   */
  getProgress(): number {
    return this.resumable.progress() * 100;
  }

  /**
   * Get upload statistics.
   */
  getStats(): {
    isUploading: boolean;
    progress: number;
    files: Resumable.ResumableFile[];
  } {
    return {
      isUploading: this.resumable.isUploading(),
      progress: this.resumable.progress() * 100,
      files: this.resumable.files
    };
  }
}

/**
 * Create a new chunked uploader instance.
 */
export function createChunkedUploader(
  apiBase: string,
  options?: ChunkedUploadOptions
): ChunkedUploader {
  return new ChunkedUploader(apiBase, options);
}

/**
 * Upload a file with automatic chunked upload for large files.
 */
export async function uploadFileWithChunking(
  file: File,
  apiBase: string,
  progressCallback?: (progress: UploadProgress) => void,
  options?: ChunkedUploadOptions
): Promise<UploadResult> {
  const uploader = createChunkedUploader(apiBase, options);
  return uploader.uploadFile(file, progressCallback);
}