'use client';

import React, { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import { DataGrid, GridColDef, GridRowsProp, GridCellEditStopReasons } from '@mui/x-data-grid';
import { Box, Typography, Button, Paper, Alert, CircularProgress } from '@mui/material';
import { getDocumentArtifacts, updateArtifact } from '../../../src/lib/api';

interface Artifact {
  id: string;
  kind: string;
  page: number;
  engine: string;
  payload: any;
  status: string;
}

interface TableRow {
  id: string;
  [key: string]: any;
}

export default function ReviewPage() {
  const params = useParams();
  const docId = params.id as string;
  
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [selectedArtifact, setSelectedArtifact] = useState<Artifact | null>(null);
  const [tableRows, setTableRows] = useState<TableRow[]>([]);
  const [tableColumns, setTableColumns] = useState<GridColDef[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadArtifacts();
  }, [docId]);

  const loadArtifacts = async () => {
    try {
      setLoading(true);
      const response = await getDocumentArtifacts(docId);
      const tableArtifacts = response.artifacts.filter((a: Artifact) => a.kind === 'table');
      setArtifacts(tableArtifacts);
      
      if (tableArtifacts.length > 0) {
        selectArtifact(tableArtifacts[0]);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load artifacts');
    } finally {
      setLoading(false);
    }
  };

  const selectArtifact = (artifact: Artifact) => {
    setSelectedArtifact(artifact);
    
    if (artifact.payload && artifact.payload.rows) {
      const rows = artifact.payload.rows;
      
      if (rows.length > 0) {
        // Create columns from header row
        const headerRow = rows[0];
        const columns: GridColDef[] = headerRow.map((header: string, index: number) => ({
          field: `col_${index}`,
          headerName: header || `Column ${index + 1}`,
          width: 150,
          editable: true,
        }));
        
        // Create data rows
        const dataRows: TableRow[] = rows.slice(1).map((row: any[], rowIndex: number) => {
          const rowData: TableRow = { id: `row_${rowIndex}` };
          row.forEach((cell: any, colIndex: number) => {
            rowData[`col_${colIndex}`] = cell || '';
          });
          return rowData;
        });
        
        setTableColumns(columns);
        setTableRows(dataRows);
      } else {
        setTableColumns([]);
        setTableRows([]);
      }
    } else {
      setTableColumns([]);
      setTableRows([]);
    }
  };

  const handleCellEdit = (params: any) => {
    const { id, field, value } = params;
    
    setTableRows(prev => 
      prev.map(row => 
        row.id === id ? { ...row, [field]: value } : row
      )
    );
  };

  const saveChanges = async () => {
    if (!selectedArtifact) return;
    
    try {
      setSaving(true);
      
      // Reconstruct the table data from the grid
      const headerRow = tableColumns.map(col => col.headerName);
      const dataRows = tableRows.map(row => 
        tableColumns.map(col => row[col.field] || '')
      );
      
      const updatedPayload = {
        ...selectedArtifact.payload,
        rows: [headerRow, ...dataRows]
      };
      
      await updateArtifact(selectedArtifact.id, {
        payload: updatedPayload,
        status: 'reviewed'
      });
      
      // Update local state
      setArtifacts(prev => 
        prev.map(artifact => 
          artifact.id === selectedArtifact.id 
            ? { ...artifact, payload: updatedPayload, status: 'reviewed' }
            : artifact
        )
      );
      
      setSelectedArtifact(prev => 
        prev ? { ...prev, payload: updatedPayload, status: 'reviewed' } : null
      );
      
      alert('Changes saved successfully!');
      
    } catch (err: any) {
      setError(err.message || 'Failed to save changes');
    } finally {
      setSaving(false);
    }
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
        Document Review
      </Typography>
      
      <Typography variant="h6" color="textSecondary" gutterBottom>
        Document ID: {docId}
      </Typography>

      {artifacts.length === 0 ? (
        <Alert severity="info">No table artifacts found for this document.</Alert>
      ) : (
        <Box display="flex" gap={3} height="calc(100vh - 200px)">
          {/* Left Panel - Preview (placeholder) */}
          <Paper sx={{ flex: 1, p: 2, display: 'flex', flexDirection: 'column' }}>
            <Typography variant="h6" gutterBottom>
              Preview
            </Typography>
            <Box 
              flex={1} 
              display="flex" 
              alignItems="center" 
              justifyContent="center"
              bgcolor="grey.100"
              borderRadius={1}
            >
              <Typography color="textSecondary">
                Preview image will be displayed here
              </Typography>
            </Box>
            
            {/* Artifact selector */}
            <Box mt={2}>
              <Typography variant="subtitle2" gutterBottom>
                Select Table:
              </Typography>
              {artifacts.map((artifact, index) => (
                <Button
                  key={artifact.id}
                  variant={selectedArtifact?.id === artifact.id ? "contained" : "outlined"}
                  size="small"
                  onClick={() => selectArtifact(artifact)}
                  sx={{ mr: 1, mb: 1 }}
                >
                  Page {artifact.page} ({artifact.engine})
                </Button>
              ))}
            </Box>
          </Paper>

          {/* Right Panel - Data Grid */}
          <Paper sx={{ flex: 1, p: 2, display: 'flex', flexDirection: 'column' }}>
            <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
              <Typography variant="h6">
                Table Editor
              </Typography>
              <Button
                variant="contained"
                onClick={saveChanges}
                disabled={saving || !selectedArtifact}
              >
                {saving ? 'Saving...' : 'Save Changes'}
              </Button>
            </Box>

            {selectedArtifact && (
              <Box mb={2}>
                <Typography variant="body2" color="textSecondary">
                  Page {selectedArtifact.page} • Engine: {selectedArtifact.engine} • Status: {selectedArtifact.status}
                </Typography>
              </Box>
            )}

            <Box flex={1}>
              {tableRows.length > 0 && tableColumns.length > 0 ? (
                <DataGrid
                  rows={tableRows}
                  columns={tableColumns}
                  onCellEditStop={(params, event) => {
                    if (event.reason === GridCellEditStopReasons.cellFocusOut) {
                      handleCellEdit(params);
                    }
                  }}
                  sx={{ 
                    '& .MuiDataGrid-cell': { 
                      fontSize: '0.875rem' 
                    }
                  }}
                />
              ) : (
                <Box 
                  display="flex" 
                  alignItems="center" 
                  justifyContent="center" 
                  height="100%"
                  bgcolor="grey.50"
                  borderRadius={1}
                >
                  <Typography color="textSecondary">
                    {selectedArtifact ? 'No table data available' : 'Select a table to edit'}
                  </Typography>
                </Box>
              )}
            </Box>
          </Paper>
        </Box>
      )}
    </Box>
  );
}