import React from 'react';
import { Message } from '../types';
import MetadataBadge from './MetadataBadge';

interface MessageBubbleProps {
  message: Message;
}

const MessageBubble: React.FC<MessageBubbleProps> = ({ message }) => {
  if (message.role === 'user') {
    return (
      <div className="message-row user-row">
        <div className="bubble user-bubble">{message.content}</div>
      </div>
    );
  }

  if (message.role === 'error') {
    return (
      <div className="message-row assistant-row">
        <div className="bubble error-bubble">
          <span className="error-icon">⚠️</span> {message.content}
        </div>
      </div>
    );
  }

  // assistant
  return (
    <div className="message-row assistant-row">
      <div data-testid="assistant-message" className="bubble assistant-bubble">
        <div className="assistant-content">{message.content}</div>
        {message.metadata && <MetadataBadge metadata={message.metadata} />}
      </div>
    </div>
  );
};

export default MessageBubble;
