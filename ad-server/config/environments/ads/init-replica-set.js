// Local development only. Validate existing configuration; never force reconfigure it.
const setName = "ads-rs";
const memberHost = "localhost:27017";
const admin = db.getSiblingDB("admin");

function fail(message) {
  throw new Error(message);
}

function waitFor(message, predicate, timeoutMs = 90000) {
  const deadline = Date.now() + timeoutMs;
  let lastError = "";
  while (Date.now() < deadline) {
    try {
      if (predicate()) return;
    } catch (error) {
      lastError = error.message;
    }
    sleep(1000);
  }
  fail(`${message}${lastError ? ` Last error: ${lastError}` : ""}`);
}

function readConfiguration() {
  try {
    return admin.runCommand({ replSetGetConfig: 1 }).config;
  } catch (error) {
    if (error.code === 94 || error.codeName === "NotYetInitialized") return null;
    throw error;
  }
}

function validateConfiguration(config) {
  const member = config?.members?.[0];
  if (
    config?._id !== setName ||
    config?.members?.length !== 1 ||
    member?._id !== 0 ||
    member?.host !== memberHost ||
    member?.arbiterOnly === true ||
    member?.hidden === true ||
    (member?.priority ?? 1) <= 0 ||
    (member?.votes ?? 1) !== 1
  ) {
    fail(
      `Existing replica set does not match ${setName} / ${memberHost}. ` +
        "Configuration and stored data were left unchanged. Check the volume and server configuration."
    );
  }
}

waitFor("MongoDB did not become reachable within 90 seconds.", () => {
  return admin.runCommand({ ping: 1 }).ok === 1;
});

const options = admin.runCommand({ getCmdLineOpts: 1 });
if (options.parsed?.replication?.replSetName !== setName) {
  fail(`mongod must be started with --replSet ${setName}.`);
}

let configuration = readConfiguration();
if (configuration === null) {
  try {
    admin.runCommand({
      replSetInitiate: {
        _id: setName,
        members: [{ _id: 0, host: memberHost }],
      },
    });
  } catch (error) {
    // Another initializer may have completed between the read and initiate calls.
    if (error.code !== 23 && error.codeName !== "AlreadyInitialized") throw error;
  }
  configuration = readConfiguration();
}
validateConfiguration(configuration);

waitFor("Replica set did not elect a primary within 90 seconds.", () => {
  const hello = admin.runCommand({ hello: 1 });
  return hello.setName === setName && hello.isWritablePrimary === true;
});

print(`${setName} is configured and writable (${memberHost}).`);
