// Preloaded into every engine process: samples the CPU from start; SIGUSR2 writes what was sampled since the
// last signal to /prof/<pid>-<n>.cpuprofile and starts afresh.
const inspector = require('inspector');
const fs = require('fs');
const session = new inspector.Session();
session.connect();
let n = 0;
session.post('Profiler.enable', () => session.post('Profiler.setSamplingInterval', { interval: 500 }, () => session.post('Profiler.start')));
process.on('SIGUSR2', () => {
  session.post('Profiler.stop', (err, res) => {
    if (!err) fs.writeFileSync(`/prof/${process.pid}-${n++}.cpuprofile`, JSON.stringify(res.profile));
    session.post('Profiler.start');
  });
});
