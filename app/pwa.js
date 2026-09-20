// Keep opening the original file directly supported alongside HTTPS hosting.
if ('serviceWorker' in navigator && ['https:', 'http:'].includes(location.protocol)) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('./sw.js').catch(error => {
      console.warn('Offline mode unavailable:', error);
    });
  });
}
