FROM mcr.microsoft.com/playwright:v1.49.1-noble AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY tsconfig.server.json tsconfig.dashboard.json ./
COPY scripts ./scripts
COPY src ./src
RUN npm run build && npm prune --omit=dev

FROM mcr.microsoft.com/playwright:v1.49.1-noble
ENV NODE_ENV=production \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    POKEIDLE_CONFIG=/app/config.yaml
WORKDIR /app
COPY --from=build /app/package.json /app/package-lock.json ./
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/dist ./dist
RUN mkdir -p /app/data && chown -R pwuser:pwuser /app
USER pwuser
EXPOSE 8787
CMD ["node", "dist/server/main.js"]
