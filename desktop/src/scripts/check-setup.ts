import { validateRuntimeLayout } from "../backend/paths";

const validation = validateRuntimeLayout();
console.log(JSON.stringify(validation, null, 2));
if (!validation.ready) {
  process.exitCode = 1;
}
