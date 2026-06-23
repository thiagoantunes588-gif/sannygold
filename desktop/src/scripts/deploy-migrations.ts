import { runAutomaticMigrations } from "../backend/migrations";
import { prisma } from "../backend/prisma";

async function main() {
  const result = await runAutomaticMigrations(true);
  console.log(JSON.stringify(result, null, 2));
}

main()
  .catch((error) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
