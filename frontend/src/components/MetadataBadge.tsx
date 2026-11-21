import React from 'react';
import { Metadata } from '../types';

interface MetadataBadgeProps {
  metadata: Metadata;
}

const MetadataBadge: React.FC<MetadataBadgeProps> = ({ metadata }) => {
  const isCache = metadata.resolution_source === 'LLM_CACHE';

  return (
    <div className="metadata-badge">
      <span
        data-testid="meta-source"
        className={`source-badge ${isCache ? 'cache' : 'live'}`}
      >
        {isCache ? '🔵 LLM_CACHE' : '🟢 LIVE_INFERENCE'}
      </span>
      <span className="meta-item">
        <span className="meta-label">Model:</span>
        <span data-testid="meta-model" className="meta-value">
          {metadata.model}
        </span>
      </span>
      <span className="meta-item">
        <span className="meta-label">Latency:</span>
        <span data-testid="meta-latency" className="meta-value">
          {metadata.latency_ms} ms
        </span>
      </span>
      <span className="meta-item">
        <span className="meta-label">Tokens:</span>
        <span className="meta-value">
          ↑{' '}
          <span data-testid="meta-input-tokens">{metadata.input_tokens}</span>{' '}
          in / ↓{' '}
          <span data-testid="meta-output-tokens">{metadata.output_tokens}</span>{' '}
          out
        </span>
      </span>
    </div>
  );
};

export default MetadataBadge;
