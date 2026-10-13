function configuredCredentials() {
  const email = process.env.FITGATE_TEST_EMAIL || process.env.FITGATE_SMOKE_EMAIL;
  const password = process.env.FITGATE_TEST_PASSWORD || process.env.FITGATE_SMOKE_PASSWORD;
  if (!email || !password) {
    throw new Error('Set FITGATE_TEST_EMAIL and FITGATE_TEST_PASSWORD locally; never commit account credentials.');
  }
  return {email, password};
}
module.exports = {configuredCredentials};
