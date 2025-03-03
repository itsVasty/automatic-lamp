import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

import { GoogleOAuthProvider } from '@react-oauth/google';
import { GoogleLoginGate } from './auth.tsx';

const clinetId = "931931453280-v0r0kbqcp6ndtrm4vu87jst27fati0bi.apps.googleusercontent.com"

createRoot(document.getElementById('root')!).render(
  //Wrap in GoogleOAuth to enable Google Authentication
  <StrictMode>
    <GoogleOAuthProvider clientId={clinetId}>
      <GoogleLoginGate>
        <App />
      </GoogleLoginGate>
    </GoogleOAuthProvider>
  </StrictMode>,
)
