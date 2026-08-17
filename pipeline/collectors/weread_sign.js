#!/usr/bin/env node
// Generates x-wrpa-0 header value for WeRead API requests.
// Usage: node weread_sign.js <path> <cookie> <referer>
// Outputs the header value to stdout.

const fs = require('fs');
const path = require('path');

const [,, reqPath, cookie, referer] = process.argv;
if (!reqPath) {
  process.stderr.write('Usage: node weread_sign.js <path> <cookie> <referer>\n');
  process.exit(1);
}

const wpaPath = path.join(__dirname, 'wpa-1.0.5.js');
if (!fs.existsSync(wpaPath)) {
  process.stderr.write('wpa-1.0.5.js not found at: ' + wpaPath + '\n');
  process.exit(1);
}

const code = fs.readFileSync(wpaPath, 'utf8');

// Redirect console.log to stderr so only the signature value goes to stdout
const _origLog = console.log;
console.log = (...args) => process.stderr.write(args.join(' ') + '\n');

global.window = global;
global.document = {
  cookie: cookie || '',
  getElementById: () => null,
  createElement: () => ({ style: {}, appendChild: () => {}, href: '' }),
  head: { appendChild: () => {} },
  body: { appendChild: () => {} },
  readyState: 'complete',
  addEventListener: () => {},
};
global.navigator = {
  userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36',
  language: 'zh-CN',
  platform: 'Win32',
  cookieEnabled: true,
};
global.location = {
  href: referer || 'https://weread.qq.com/',
  hostname: 'weread.qq.com',
  protocol: 'https:',
  pathname: referer ? new URL(referer).pathname : '/',
  host: 'weread.qq.com',
};
global.XMLHttpRequest = function () {
  this.open = () => {};
  this.send = () => {};
  this.setRequestHeader = () => {};
  this.addEventListener = () => {};
};
global.localStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };
global.sessionStorage = { getItem: () => null, setItem: () => {}, removeItem: () => {} };
global.screen = { width: 1920, height: 1080, colorDepth: 24 };
global.history = { length: 1 };
global.MutationObserver = function () { this.observe = () => {}; };
global.requestAnimationFrame = (cb) => setTimeout(cb, 16);

eval(code); // eslint-disable-line no-eval

const wrpa = global.__WRPA__;
if (!wrpa || typeof wrpa.sr !== 'function') {
  process.stderr.write('__WRPA__.sr not available\n');
  process.exit(1);
}

wrpa.sr(reqPath).then((parts) => {
  if (!parts || !parts.length) {
    process.stderr.write('sr returned empty result\n');
    process.exit(1);
  }
  process.stdout.write(parts.join(',') + '\n');
}).catch((err) => {
  process.stderr.write('sr error: ' + err.message + '\n');
  process.exit(1);
});
