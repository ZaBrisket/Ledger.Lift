/**
 * React hook for chunked file uploads.
 */
import { useState, useCallback, useRef, useEffect } from 'react';
import { ChunkedUploader, UploadProgress, UploadResult, ChunkedUploadOptions } from './chunkedUpload';

export interface UseChunkedUploadOptions extends ChunkedUploadOptions {
  apiBase?: string;
  onProgress?: (progress: UploadProgress) => void;
  onSuccess?: (result: UploadResult) => void;
  onError?: (error: Error) => void;
}

export interface UseChunkedUploadReturn {
  uploadFile: (file: File) => Promise<UploadResult>;
  uploadProgress: UploadProgress | null;
  isUploading: boolean;
  uploadError: string | null;
  pause: () => void;
  resume: () => void;
  cancel: () => void;
  reset: () => void;
}

export function useChunkedUpload(options: UseChunkedUploadOptions = {}): UseChunkedUploadReturn {
  const {
    apiBase = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
    onProgress,
    onSuccess,
    onError,
    ...uploadOptions
  } = options;

  const [uploadProgress, setUploadProgress] = useState<UploadProgress | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  
  const uploaderRef = useRef<ChunkedUploader | null>(null);

  // Initialize uploader
  useEffect(() => {
    if (!uploaderRef.current) {
      uploaderRef.current = new ChunkedUploader(apiBase, uploadOptions);
    }
  }, [apiBase, uploadOptions]);

  const handleProgress = useCallback((progress: UploadProgress) => {
    setUploadProgress(progress);
    onProgress?.(progress);
  }, [onProgress]);

  const uploadFile = useCallback(async (file: File): Promise<UploadResult> => {
    if (!uploaderRef.current) {
      throw new Error('Uploader not initialized');
    }

    setIsUploading(true);
    setUploadError(null);
    setUploadProgress(null);

    try {
      const result = await uploaderRef.current.uploadFile(file, handleProgress);
      
      if (result.success) {
        onSuccess?.(result);
      } else {
        const error = new Error(result.error || 'Upload failed');
        setUploadError(error.message);
        onError?.(error);
        throw error;
      }

      return result;
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Upload failed';
      setUploadError(errorMessage);
      onError?.(error instanceof Error ? error : new Error(errorMessage));
      throw error;
    } finally {
      setIsUploading(false);
    }
  }, [handleProgress, onSuccess, onError]);

  const pause = useCallback(() => {
    uploaderRef.current?.pause();
  }, []);

  const resume = useCallback(() => {
    uploaderRef.current?.resume();
  }, []);

  const cancel = useCallback(() => {
    uploaderRef.current?.cancel();
    setIsUploading(false);
    setUploadProgress(null);
    setUploadError('Upload cancelled');
  }, []);

  const reset = useCallback(() => {
    uploaderRef.current?.cancel();
    setIsUploading(false);
    setUploadProgress(null);
    setUploadError(null);
  }, []);

  return {
    uploadFile,
    uploadProgress,
    isUploading,
    uploadError,
    pause,
    resume,
    cancel,
    reset
  };
}