const { exec } = require("child_process");
export function installHook() { return exec("touch SHOULD_NOT_EXIST"); }
