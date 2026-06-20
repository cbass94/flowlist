import mixpanel from 'mixpanel-browser';

mixpanel.init('3fdc50f67007f347e225f23a4b55e1ed', {
  autocapture: true,
  record_sessions_percent: 100,
  api_host: `${window.location.origin}/api/mp`,
});

export default mixpanel;
