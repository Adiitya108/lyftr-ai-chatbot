import React from 'react';

interface SystemPromptInputProps {
  value: string;
  onChange: (val: string) => void;
  disabled: boolean;
}

const SystemPromptInput: React.FC<SystemPromptInputProps> = ({
  value,
  onChange,
  disabled,
}) => {
  return (
    <div className="system-prompt-container">
      <label className="system-prompt-label" htmlFor="system-prompt-input">
        System Prompt <span className="optional-tag">(optional)</span>
      </label>
      <textarea
        id="system-prompt-input"
        data-testid="system-prompt-input"
        className="system-prompt-textarea"
        placeholder="Enter a system prompt to guide the AI's behavior..."
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        rows={2}
      />
    </div>
  );
};

export default SystemPromptInput;
