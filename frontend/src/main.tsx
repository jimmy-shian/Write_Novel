import React from 'react';
import ReactDOM from 'react-dom/client';
import { App } from './App';
import './styles/opendesign.css';
import './styles/selection.css';

const rootElement = document.getElementById('root');

if (rootElement) {
  const root = ReactDOM.createRoot(rootElement);
  root.render(
    <React.StrictMode>
      <App />
    </React.StrictMode>
  );
}
