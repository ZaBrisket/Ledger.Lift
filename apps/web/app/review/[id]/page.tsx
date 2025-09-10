'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { useParams } from 'next/navigation';
import { DataGrid, GridColDef, GridRowParams } from '@mui/x-data-grid';
import { Box, Paper, Typography, Button, Alert, CircularProgress } from '@mui/material';
import { getDocumentArtifacts, getDocumentPreviews, updateArtifact } from '../../../src/lib/api';

interface Artifact {
  id: string;
  kind: string;
  page: number;
  engine: string;
  payload: any;
  status: string;
  created_at: string;
  updated_at: string;
}

interface PreviewData {
  images: string[];
}

export default function ReviewPage() {
  const params = useParams();
  const documentId = params.id as string;
  
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [previews, setPreviews] = useState<PreviewData>({ images: [] });
  const [selectedArtifact, setSelectedArtifact] = useState<Artifact | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Load data on mount
  useEffect(() => {
    const loadData = async () => {
      try {
        setLoading(true);
        const [artifactsData, previewsData] = await Promise.all([
          getDocumentArtifacts(documentId),
          getDocumentPreviews(documentId)
        ]);
        setArtifacts(artifactsData);
        setPreviews(previewsData);
      } catch (err: any) {
        setError(err.message || 'Failed to load data');
      } finally {
        setLoading(false);
      }
    };

    if (documentId) {
      loadData();
    }
  }, [documentId]);

  // Handle artifact selection
  const handleRowClick = (params: GridRowParams) => {
    const artifact = artifacts.find(a => a.id === params.id);
    setSelectedArtifact(artifact || null);
  };

  // Handle saving changes
  const handleSave = useCallback(async () => {
    if (!selectedArtifact) return;

    try {
      setSaving(true);
      await updateArtifact(selectedArtifact.id, {
        payload: selectedArtifact.payload,
        status: 'completed'
      });
      
      // Update local state
      setArtifacts(prev => 
        prev.map(a => 
          a.id === selectedArtifact.id 
            ? { ...a, payload: selectedArtifact.payload, status: 'completed' }
            : a
        )
      );
      
      alert('Changes saved successfully!');
    } catch (err: any) {
      alert(`Failed to save: ${err.message}`);
    } finally {
      setSaving(false);
    }
  }, [selectedArtifact]);

  // Convert table data to DataGrid format
  const getTableRows = (artifact: Artifact) => {
    if (!artifact || artifact.kind !== 'table' || !artifact.payload.data) {
      return [];
    }

    const { data, headers } = artifact.payload;
    return data.map((row: any[], index: number) => ({
      id: index,
      ...row.reduce((acc, cell, cellIndex) => {
        const header = headers[cellIndex] || `Column ${cellIndex + 1}`;
        acc[header] = cell;
        return acc;
      }, {} as any)
    }));
  };

  const getTableColumns = (artifact: Artifact): GridColDef[] => {
    if (!artifact || artifact.kind !== 'table' || !artifact.payload.headers) {
      return [];
    }

    return artifact.payload.headers.map((header: string, index: number) => ({
      field: header,
      headerName: header,
      width: 150,
      editable: true,
    }));
  };

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="400px">
        <CircularProgress />
      </Box>
    );
  }

  if (error) {
    return (
      <Box p={3}>
        <Alert severity="error">{error}</Alert>
      </Box>
    );
  }

  return (
    <Box p={3}>
      <Typography variant="h4" gutterBottom>
        Document Review - {documentId}
      </Typography>
      
      <Box display="flex" gap={2} mt={2}>
        {/* Left side - Preview images */}
        <Paper sx={{ p: 2, flex: 1, minHeight: 400 }}>
          <Typography variant="h6" gutterBottom>
            Document Preview
          </Typography>
          {previews.images.length > 0 ? (
            <Box>
              {previews.images.map((imageUrl, index) => (
                <Box key={index} mb={2}>
                  <img 
                    src={imageUrl} 
                    alt={`Page ${index + 1}`}
                    style={{ maxWidth: '100%', height: 'auto', border: '1px solid #ccc' }}
                  />
                  <Typography variant="caption" display="block" textAlign="center">
                    Page {index + 1}
                  </Typography>
                </Box>
              ))}
            </Box>
          ) : (
            <Typography color="text.secondary">
              No preview images available
            </Typography>
          )}
        </Paper>

        {/* Right side - Artifacts list and editor */}
        <Paper sx={{ p: 2, flex: 1, minHeight: 400 }}>
          <Typography variant="h6" gutterBottom>
            Extracted Data
          </Typography>
          
          {artifacts.length === 0 ? (
            <Typography color="text.secondary">
              No artifacts found for this document
            </Typography>
          ) : (
            <Box>
              {/* Artifacts list */}
              <Box mb={2}>
                <Typography variant="subtitle2" gutterBottom>
                  Available Artifacts:
                </Typography>
                {artifacts.map((artifact) => (
                  <Button
                    key={artifact.id}
                    variant={selectedArtifact?.id === artifact.id ? "contained" : "outlined"}
                    size="small"
                    onClick={() => setSelectedArtifact(artifact)}
                    sx={{ mr: 1, mb: 1 }}
                  >
                    {artifact.kind} (Page {artifact.page}) - {artifact.engine}
                  </Button>
                ))}
              </Box>

              {/* Selected artifact editor */}
              {selectedArtifact && (
                <Box>
                  <Typography variant="subtitle2" gutterBottom>
                    Editing: {selectedArtifact.kind} from Page {selectedArtifact.page}
                  </Typography>
                  
                  {selectedArtifact.kind === 'table' && selectedArtifact.payload.data ? (
                    <Box>
                      <DataGrid
                        rows={getTableRows(selectedArtifact)}
                        columns={getTableColumns(selectedArtifact)}
                        pageSizeOptions={[5, 10, 25]}
                        initialState={{
                          pagination: { paginationModel: { pageSize: 10 } },
                        }}
                        onCellEditCommit={(params) => {
                          // Update the artifact payload when cells are edited
                          const newData = [...selectedArtifact.payload.data];
                          const rowIndex = params.id as number;
                          const field = params.field;
                          const value = params.value;
                          
                          const headerIndex = selectedArtifact.payload.headers.indexOf(field);
                          if (headerIndex >= 0) {
                            newData[rowIndex][headerIndex] = value;
                            
                            setSelectedArtifact({
                              ...selectedArtifact,
                              payload: {
                                ...selectedArtifact.payload,
                                data: newData
                              }
                            });
                          }
                        }}
                        sx={{ height: 300, width: '100%' }}
                      />
                      
                      <Box mt={2}>
                        <Button
                          variant="contained"
                          onClick={handleSave}
                          disabled={saving}
                          sx={{ mr: 1 }}
                        >
                          {saving ? 'Saving...' : 'Save Changes'}
                        </Button>
                        <Button
                          variant="outlined"
                          onClick={() => setSelectedArtifact(null)}
                        >
                          Cancel
                        </Button>
                      </Box>
                    </Box>
                  ) : (
                    <Typography color="text.secondary">
                      This artifact type cannot be edited in the grid view.
                    </Typography>
                  )}
                </Box>
              )}
            </Box>
          )}
        </Paper>
      </Box>
    </Box>
  );
}