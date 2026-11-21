import React from 'react';
import ChatWindow from './components/ChatWindow';

const App: React.FC = () => {
  return (
    <div className="app-container">
      <header className="app-header">
        <div className="header-content">
          <span className="logo">🚀</span>
          <h1 className="app-title">Lyftr AI</h1>
          <span className="header-subtitle">Powered by Gemini</span>
        </div>
      </header>
      <main className="app-main">
        <ChatWindow />
      </main>
    </div>
  );
};

export default App;
