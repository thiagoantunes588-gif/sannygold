import bcrypt from "bcryptjs";
import { Role, UserStatus } from "@prisma/client";
import { randomBytes } from "node:crypto";
import { prisma } from "./prisma";
import { logger } from "./logger";
import { permissionCatalog, permissionsForRole } from "./permissions";

async function seedPermissions() {
  for (const permission of permissionCatalog) {
    await prisma.permission.upsert({
      where: { key: permission.key },
      create: permission,
      update: {
        module: permission.module,
        description: permission.description,
      },
    });
  }

  for (const role of Object.values(Role)) {
    const permissions = permissionsForRole(role);
    if (permissions.includes("*")) {
      for (const permission of permissionCatalog) {
        await prisma.rolePermission.upsert({
          where: { role_permissionKey: { role, permissionKey: permission.key } },
          create: { role, permissionKey: permission.key },
          update: {},
        });
      }
      continue;
    }
    for (const permissionKey of permissions) {
      await prisma.rolePermission.upsert({
        where: { role_permissionKey: { role, permissionKey } },
        create: { role, permissionKey },
        update: {},
      });
    }
  }
}

async function main() {
  await seedPermissions();
  const email = (process.env.SANNYSYSTEM_ADMIN_EMAIL || "admin@sannysystem.local").trim().toLowerCase();
  const providedPassword = process.env.SANNYSYSTEM_ADMIN_PASSWORD || "";
  const password = providedPassword || randomBytes(14).toString("base64url");
  const passwordHash = await bcrypt.hash(password, 12);

  const user = await prisma.user.upsert({
    where: { email },
    create: {
      name: "Administrador SannySystem",
      login: email,
      email,
      role: Role.ADMINISTRADOR,
      status: UserStatus.ATIVO,
      mustChangePassword: true,
      passwordHash,
      passwordChangedAt: new Date(),
    },
    update: {
      login: email,
      role: Role.ADMINISTRADOR,
      status: UserStatus.ATIVO,
      ...(providedPassword ? { passwordHash, mustChangePassword: true, passwordChangedAt: new Date() } : {}),
    },
  });

  logger.info("Administrador inicial pronto", { email: user.email });
  if (!providedPassword) {
    console.log(`Senha temporaria do administrador ${email}: ${password}`);
  }
}

main()
  .catch((error) => {
    console.error(error);
    process.exitCode = 1;
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
