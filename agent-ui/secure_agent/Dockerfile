# Stage 1 — install dependencies
FROM node:20-alpine AS deps
WORKDIR /app
COPY package*.json ./
RUN npm install --legacy-peer-deps

# Stage 2 — build
FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# NEXT_PUBLIC vars must be available at build time
ARG NEXT_PUBLIC_SANITIZER_API_URL=http://localhost:8003
ENV NEXT_PUBLIC_SANITIZER_API_URL=${NEXT_PUBLIC_SANITIZER_API_URL}

RUN npm run build

# Ensure public/ exists so the COPY in the runner stage never fails
RUN mkdir -p /app/public

# Stage 3 — production runner (uses Next.js standalone output)
FROM node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production

# Copy the standalone build output
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000

ENV PORT=3000
ENV HOSTNAME=0.0.0.0

CMD ["node", "server.js"]
