// Keep direct file opening supported; refresh CSS without interrupting a lesson.
if ('serviceWorker' in navigator && ['https:', 'http:'].includes(location.protocol)) {
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    const link = document.querySelector('link[rel="stylesheet"]');
    if (link) {
      const url = new URL(link.href);
      url.searchParams.set('refresh', Date.now());
      link.href = url.href;
    }
  });
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('./sw.js', {updateViaCache: 'none'}).then(reg => {
      const activate = () => reg.waiting?.postMessage('ACTIVATE_UPDATE');
      activate();
      reg.addEventListener('updatefound', () => {
        const worker = reg.installing;
        worker?.addEventListener('statechange', () => {
          if (worker.state === 'installed') activate();
        });
      });
      reg.update().catch(console.warn);
    }).catch(error => console.warn('Offline mode unavailable:', error));
  });
}
