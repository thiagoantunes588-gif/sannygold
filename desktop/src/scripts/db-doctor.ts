import { createPrismaClient, databaseHealth, sanitizedDatabaseConfig } from "../backend/database";

async function main() {
  const prisma = createPrismaClient();
  const health = await databaseHealth(prisma);
  console.log(JSON.stringify({ database: sanitizedDatabaseConfig(), health }, null, 2));
  if (!health.ok) process.exitCode = 1;
  await prisma.$disconnect();
}

main()
  .catch((error) => {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  });
