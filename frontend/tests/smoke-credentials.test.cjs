const test = require('node:test');
const assert = require('node:assert/strict');
const {configuredCredentials} = require('./smoke-credentials.cjs');

test('Smoke accounts require explicit environment credentials without a built-in password', () => {
  const names=['FITGATE_TEST_EMAIL','FITGATE_TEST_PASSWORD','FITGATE_SMOKE_EMAIL','FITGATE_SMOKE_PASSWORD'];
  const saved=Object.fromEntries(names.map(name=>[name,process.env[name]]));
  try {
    for(const name of names)delete process.env[name];
    assert.throws(configuredCredentials,/Set FITGATE_TEST_EMAIL/);
    process.env.FITGATE_TEST_EMAIL='isolated@example.test';
    process.env.FITGATE_TEST_PASSWORD='synthetic-test-only';
    assert.deepEqual(configuredCredentials(),{email:'isolated@example.test',password:'synthetic-test-only'});
  }finally{
    for(const name of names){if(saved[name]===undefined)delete process.env[name];else process.env[name]=saved[name];}
  }
});
