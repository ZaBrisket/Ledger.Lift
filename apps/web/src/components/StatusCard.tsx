'use client';

import React from 'react';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Typography from '@mui/material/Typography';

export default function StatusCard({ status }: { status: string }) {
  return (
    <Card variant="outlined">
      <CardContent>
        <Typography variant="h6">Status</Typography>
        <Typography variant="body2">{status}</Typography>
      </CardContent>
    </Card>
  );
}
