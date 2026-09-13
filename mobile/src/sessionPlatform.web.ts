// The hosted browser always uses its own origin. No build-time credential or
// cross-site API URL can redirect a private session to a different service.
export const webSession = true;
export const apiBaseUrl = typeof window !== 'undefined' ? window.location.origin : 'http://localhost:8000';
