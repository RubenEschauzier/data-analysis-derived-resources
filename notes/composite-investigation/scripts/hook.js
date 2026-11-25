// Preloaded into every engine process: samples the CPU from start; SIGUSR2 writes what was sampled since the
// last signal to /prof/<pid>-<n>.cpuprofile and starts afresh. Each profile also gets startWallMs: the wall-clock
// time (ms) matching its startTime, so samples can be placed on the query's timeline.
const inspector = require('inspector');
const fs = require('fs');
const session = new inspector.Session();
session.connect();
let n = 0;
// V8 profile timestamps and process.hrtime both read the monotonic clock (µs / ns)
const wallOffsetMs = () => Date.now() - Number(process.hrtime.bigint() / 1000000n);
session.post('Profiler.enable', () => session.post('Profiler.setSamplingInterval', { interval: 500 }, () => session.post('Profiler.start')));
process.on('SIGUSR2', () => {
  session.post('Profiler.stop', (err, res) => {
    if (!err) {
      res.profile.startWallMs = res.profile.startTime / 1000 + wallOffsetMs();
      fs.writeFileSync(`/prof/${process.pid}-${n++}.cpuprofile`, JSON.stringify(res.profile));
    }
    session.post('Profiler.start');
  });
});
