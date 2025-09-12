/**
 * Chunked upload component with drag-and-drop support.
 */
import React, { useCallback, useState } from 'react';
import { useDropzone } from 'react-dropzone';
import {
  Box,
  Paper,
  Typography,
  LinearProgress,
  Button,
  Alert,
  Chip,
  IconButton,
  Tooltip
} from '@mui/material';
import {
  CloudUpload as UploadIcon,
  Pause as PauseIcon,
  PlayArrow as PlayIcon,
  Cancel as CancelIcon,
  CheckCircle as SuccessIcon,
  Error as ErrorIcon
} from '@mui/icons-material';
import { useChunkedUpload, UploadProgress } from '../lib/useChunkedUpload';

export interface ChunkedUploadProps {
  onUploadSuccess?: (result: { documentId: string; filename: string }) => void;
  onUploadError?: (error: string) => void;
  maxFileSize?: number; // in bytes
  acceptedFileTypes?: string[];
  multiple?: boolean;
  disabled?: boolean;
}

export function ChunkedUpload({
  onUploadSuccess,
  onUploadError,
  maxFileSize = 100 * 1024 * 1024, // 100MB default
  acceptedFileTypes = ['.pdf'],
  multiple = false,
  disabled = false
}: ChunkedUploadProps) {
  const [uploadedFiles, setUploadedFiles] = useState<Array<{
    file: File;
    result?: { documentId: string; filename: string };
    error?: string;
  }>>([]);

  const {
    uploadFile,
    uploadProgress,
    isUploading,
    uploadError,
    pause,
    resume,
    cancel,
    reset
  } = useChunkedUpload({
    onSuccess: (result) => {
      if (result.success && result.documentId) {
        onUploadSuccess?.({
          documentId: result.documentId,
          filename: result.filename
        });
      }
    },
    onError: (error) => {
      onUploadError?.(error.message);
    }
  });

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    if (disabled) return;

    // Filter files by size and type
    const validFiles = acceptedFiles.filter(file => {
      if (file.size > maxFileSize) {
        onUploadError?.(`File ${file.name} is too large (max ${Math.round(maxFileSize / 1024 / 1024)}MB)`);
        return false;
      }
      return true;
    });

    if (validFiles.length === 0) return;

    // Add files to state
    const newFiles = validFiles.map(file => ({ file }));
    setUploadedFiles(prev => [...prev, ...newFiles]);

    // Upload files
    for (const fileData of newFiles) {
      try {
        const result = await uploadFile(fileData.file);
        if (result.success && result.documentId) {
          setUploadedFiles(prev => 
            prev.map(f => 
              f.file === fileData.file 
                ? { ...f, result: { documentId: result.documentId!, filename: result.filename } }
                : f
            )
          );
        }
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : 'Upload failed';
        setUploadedFiles(prev => 
          prev.map(f => 
            f.file === fileData.file 
              ? { ...f, error: errorMessage }
              : f
          )
        );
      }
    }
  }, [disabled, maxFileSize, onUploadError, uploadFile]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: acceptedFileTypes.reduce((acc, type) => {
      acc[type] = [];
      return acc;
    }, {} as Record<string, string[]>),
    multiple,
    disabled
  });

  const formatFileSize = (bytes: number): string => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const formatProgress = (progress: UploadProgress): string => {
    return `${progress.chunksUploaded}/${progress.totalChunks} chunks (${Math.round(progress.progress)}%)`;
  };

  return (
    <Box sx={{ width: '100%' }}>
      {/* Upload Area */}
      <Paper
        {...getRootProps()}
        sx={{
          p: 4,
          textAlign: 'center',
          cursor: disabled ? 'not-allowed' : 'pointer',
          border: '2px dashed',
          borderColor: isDragActive ? 'primary.main' : 'grey.300',
          backgroundColor: isDragActive ? 'action.hover' : 'background.paper',
          transition: 'all 0.2s ease-in-out',
          '&:hover': {
            borderColor: disabled ? 'grey.300' : 'primary.main',
            backgroundColor: disabled ? 'background.paper' : 'action.hover'
          }
        }}
      >
        <input {...getInputProps()} />
        <UploadIcon sx={{ fontSize: 48, color: 'grey.400', mb: 2 }} />
        <Typography variant="h6" gutterBottom>
          {isDragActive ? 'Drop files here' : 'Drag & drop files here'}
        </Typography>
        <Typography variant="body2" color="text.secondary" gutterBottom>
          or click to select files
        </Typography>
        <Typography variant="caption" color="text.secondary">
          Max file size: {formatFileSize(maxFileSize)} • Supported: {acceptedFileTypes.join(', ')}
        </Typography>
      </Paper>

      {/* Upload Progress */}
      {isUploading && uploadProgress && (
        <Box sx={{ mt: 2 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', mb: 1 }}>
            <Typography variant="body2" sx={{ flexGrow: 1 }}>
              Uploading {uploadProgress.filename}...
            </Typography>
            <Box>
              <Tooltip title="Pause">
                <IconButton size="small" onClick={pause}>
                  <PauseIcon />
                </IconButton>
              </Tooltip>
              <Tooltip title="Cancel">
                <IconButton size="small" onClick={cancel}>
                  <CancelIcon />
                </IconButton>
              </Tooltip>
            </Box>
          </Box>
          <LinearProgress 
            variant="determinate" 
            value={uploadProgress.progress} 
            sx={{ mb: 1 }}
          />
          <Typography variant="caption" color="text.secondary">
            {formatProgress(uploadProgress)} • {formatFileSize(uploadProgress.bytesUploaded)} / {formatFileSize(uploadProgress.totalBytes)}
          </Typography>
        </Box>
      )}

      {/* Upload Error */}
      {uploadError && (
        <Alert severity="error" sx={{ mt: 2 }} onClose={reset}>
          {uploadError}
        </Alert>
      )}

      {/* Uploaded Files */}
      {uploadedFiles.length > 0 && (
        <Box sx={{ mt: 2 }}>
          <Typography variant="subtitle2" gutterBottom>
            Uploaded Files ({uploadedFiles.length})
          </Typography>
          {uploadedFiles.map((fileData, index) => (
            <Box
              key={index}
              sx={{
                display: 'flex',
                alignItems: 'center',
                p: 1,
                border: '1px solid',
                borderColor: 'divider',
                borderRadius: 1,
                mb: 1,
                backgroundColor: fileData.result ? 'success.light' : fileData.error ? 'error.light' : 'background.paper'
              }}
            >
              {fileData.result ? (
                <SuccessIcon color="success" sx={{ mr: 1 }} />
              ) : fileData.error ? (
                <ErrorIcon color="error" sx={{ mr: 1 }} />
              ) : (
                <UploadIcon color="action" sx={{ mr: 1 }} />
              )}
              
              <Box sx={{ flexGrow: 1, minWidth: 0 }}>
                <Typography variant="body2" noWrap>
                  {fileData.file.name}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {formatFileSize(fileData.file.size)}
                </Typography>
              </Box>

              {fileData.result && (
                <Chip
                  label="Success"
                  size="small"
                  color="success"
                  icon={<SuccessIcon />}
                />
              )}
              
              {fileData.error && (
                <Chip
                  label="Failed"
                  size="small"
                  color="error"
                  icon={<ErrorIcon />}
                />
              )}
            </Box>
          ))}
        </Box>
      )}

      {/* Action Buttons */}
      {isUploading && (
        <Box sx={{ mt: 2, display: 'flex', gap: 1 }}>
          <Button
            variant="outlined"
            startIcon={<PauseIcon />}
            onClick={pause}
            disabled={!isUploading}
          >
            Pause
          </Button>
          <Button
            variant="outlined"
            startIcon={<PlayIcon />}
            onClick={resume}
            disabled={!isUploading}
          >
            Resume
          </Button>
          <Button
            variant="outlined"
            color="error"
            startIcon={<CancelIcon />}
            onClick={cancel}
            disabled={!isUploading}
          >
            Cancel
          </Button>
        </Box>
      )}
    </Box>
  );
}