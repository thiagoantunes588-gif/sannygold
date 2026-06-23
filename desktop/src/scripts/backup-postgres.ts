import { createPostgresBackup } from "../backend/database-backup";
import { prisma } from "../backend/prisma";

async function main() {
  const result = await createPostgresBackup();
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
