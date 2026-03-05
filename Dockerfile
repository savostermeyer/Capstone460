# Use Node.js runtime for Express API + built frontend
FROM node:20-slim

WORKDIR /app

# Install backend dependencies first for caching
COPY package*.json ./
RUN npm install --omit=dev

# Install frontend dependencies and build static assets
COPY front-end/package*.json ./front-end/
RUN npm --prefix front-end install

# Copy source
COPY . .

# Build React app for production
RUN npm --prefix front-end run build

ENV NODE_ENV=production
EXPOSE 8080

# Cloud Run sets PORT automatically
CMD ["node", "server.js"]
