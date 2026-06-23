import { Role } from "@prisma/client";

export const permissionCatalog: Array<{ key: string; module: string; description: string }> = [
  { key: "users.manage", module: "users", description: "Criar, editar, bloquear e redefinir usuários." },
  { key: "permissions.read", module: "permissions", description: "Consultar matriz de permissões." },
  { key: "clients.read", module: "clients", description: "Consultar clientes." },
  { key: "clients.write", module: "clients", description: "Criar e editar clientes." },
  { key: "events.read", module: "events", description: "Consultar eventos." },
  { key: "events.write", module: "events", description: "Criar e editar eventos." },
  { key: "equipment.read", module: "equipment", description: "Consultar equipamentos." },
  { key: "equipment.write", module: "equipment", description: "Criar e editar equipamentos." },
  { key: "warehouse.read", module: "warehouse", description: "Consultar almoxarifado e estoque." },
  { key: "warehouse.write", module: "warehouse", description: "Movimentar estoque e registrar separações." },
  { key: "vehicles.read", module: "vehicles", description: "Consultar veículos." },
  { key: "vehicles.write", module: "vehicles", description: "Criar e editar veículos." },
  { key: "routes.read", module: "routes", description: "Consultar rotas." },
  { key: "serviceOrders.read", module: "service-orders", description: "Consultar ordens de serviço." },
  { key: "serviceOrders.write", module: "service-orders", description: "Criar e editar ordens de serviço." },
  { key: "serviceOrders.writeOwn", module: "service-orders", description: "Atualizar ordens atribuídas ao próprio usuário." },
  { key: "financial.read", module: "financial", description: "Consultar financeiro." },
  { key: "financial.write", module: "financial", description: "Criar e editar lançamentos financeiros." },
  { key: "audit.read", module: "audit", description: "Consultar auditoria." },
  { key: "logs.read", module: "logs", description: "Consultar logs operacionais." },
  { key: "database.manage", module: "database", description: "Gerenciar conexão, migrations e backups." },
  { key: "offline.queue", module: "offline", description: "Registrar ações operacionais offline e enviá-las para a fila." },
  { key: "offline.sync", module: "offline", description: "Processar fila offline, retries e conflitos de sincronização." },
  { key: "sync.export", module: "sync", description: "Exportar snapshots de sincronização." },
  { key: "sync.import", module: "sync", description: "Importar snapshots e resolver conflitos." },
];

export const roleLabels: Record<Role, string> = {
  ADMINISTRADOR: "administrador",
  OPERACAO: "operação",
  MOTORISTA: "motorista",
  FINANCEIRO: "financeiro",
  ALMOXARIFADO: "almoxarifado",
};

export const roleFromInput = (value: string | undefined): Role => {
  const normalized = String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase();

  if (["admin", "administrador"].includes(normalized)) return Role.ADMINISTRADOR;
  if (["operacao", "operacional", "operador"].includes(normalized)) return Role.OPERACAO;
  if (["motorista", "driver"].includes(normalized)) return Role.MOTORISTA;
  if (["financeiro", "finance"].includes(normalized)) return Role.FINANCEIRO;
  if (["almoxarifado", "estoque", "warehouse"].includes(normalized)) return Role.ALMOXARIFADO;
  return Role.OPERACAO;
};

const rolePermissions: Record<Role, string[]> = {
  ADMINISTRADOR: ["*"],
  OPERACAO: [
    "clients.read",
    "clients.write",
    "events.read",
    "events.write",
    "equipment.read",
    "equipment.write",
    "warehouse.read",
    "warehouse.write",
    "vehicles.read",
    "vehicles.write",
    "serviceOrders.read",
    "serviceOrders.write",
    "offline.queue",
    "offline.sync",
    "sync.export",
    "sync.import",
  ],
  MOTORISTA: [
    "events.read",
    "routes.read",
    "serviceOrders.read",
    "serviceOrders.writeOwn",
    "equipment.read",
    "offline.queue",
    "offline.sync",
    "sync.export",
  ],
  FINANCEIRO: [
    "clients.read",
    "events.read",
    "financial.read",
    "financial.write",
    "audit.read",
    "logs.read",
    "offline.sync",
    "sync.export",
  ],
  ALMOXARIFADO: [
    "equipment.read",
    "equipment.write",
    "warehouse.read",
    "warehouse.write",
    "serviceOrders.read",
    "serviceOrders.write",
    "events.read",
    "offline.queue",
    "offline.sync",
    "sync.export",
    "sync.import",
  ],
};

export function permissionsForRole(role: Role): string[] {
  return rolePermissions[role] || [];
}

export function hasPermission(role: Role, permission: string): boolean {
  const permissions = permissionsForRole(role);
  if (permissions.includes("*")) return true;
  if (permissions.includes(permission)) return true;
  const [namespace] = permission.split(".");
  return permissions.includes(`${namespace}.*`);
}
