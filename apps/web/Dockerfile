FROM node:22-alpine

ENV NEXT_TELEMETRY_DISABLED=1

WORKDIR /workspace

RUN corepack enable

COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY apps/web/package.json apps/web/package.json
RUN pnpm install --frozen-lockfile --filter @jacaranda/web...

COPY apps/web apps/web

EXPOSE 3000

CMD ["pnpm", "--filter", "@jacaranda/web", "dev"]
