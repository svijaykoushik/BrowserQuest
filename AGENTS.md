# AGENTS.md

## Project Overview
**BrowserQuest** is an open-source, HTML5/JavaScript multiplayer 2D adventure game (MMORPG) originally created by Little Workshop. It demonstrates real-time web technologies using HTML5 Canvas, WebSockets, and Node.js.

---

## Repository Structure

```
BrowserQuest/
├── bin/                 # Build utilities and RequireJS optimizer (r.js, build.sh)
├── client/              # Frontend web client (HTML5, Canvas, RequireJS, CSS, assets)
│   ├── audio/           # Sound effects and music tracks (ogg/mp3)
│   ├── config/          # Client environment configs (config_build.json-dist)
│   ├── css/             # Stylesheets for HUD, chat, and UI modals
│   ├── fonts/           # Web fonts
│   ├── img/             # UI images, textures, and spritesheet graphics
│   ├── js/              # Client JavaScript application modules (AMD/RequireJS)
│   │   ├── app.js       # UI bindings and top-level web app orchestration
│   │   ├── game.js      # Main game loop, player actions, world state
│   │   ├── gameclient.js# WebSocket network client handler
│   │   ├── renderer.js  # HTML5 Canvas 2D rendering pipeline
│   │   └── ...          # Entities, audio, pathfinding, camera, etc.
│   ├── maps/            # Client-side map data files (JSON)
│   ├── sprites/         # Sprite definition JSON metadata
│   └── index.html       # Client entry HTML
├── server/              # Node.js backend game server
│   ├── js/              # Server logic (WorldServer, entities, dispatchers)
│   │   ├── main.js      # Server entrypoint
│   │   ├── worldserver.js # World instance manager, tick loop, entity tracking
│   │   ├── ws.js        # WebSocket server wrapper
│   │   ├── player.js    # Player entity & server-side action validation
│   │   ├── mob.js       # Mob AI and combat state
│   │   ├── map.js       # Server-side collision detection and grid management
│   │   └── ...          # Items, chests, checkpoints, formulas, metrics
│   ├── maps/            # Server-side map data (world_server.json)
│   ├── config.json      # Default server configuration
│   └── config_local.json-dist # Local server configuration template
├── shared/              # Code shared across client and server
│   └── js/
│       └── gametypes.js # Enums, entity types, messages, orientations, damage types
└── tools/               # Developer tooling
    └── maps/            # Tiled Map Editor (TMX) conversion and export tools
```

---

## Architecture & Communication Flow

1. **Shared Definitions**:
   - [`shared/js/gametypes.js`](file:///home/vijaykoushik/Evee/My%20Documents/GitHub/BrowserQuest/shared/js/gametypes.js) defines protocol messages (`Types.Messages`), entity kinds (`Types.Entities`), orientations, and item identifiers used by both the client and server.

2. **Server Architecture**:
   - **Entrypoint**: [`server/js/main.js`](file:///home/vijaykoushik/Evee/My%20Documents/GitHub/BrowserQuest/server/js/main.js) initializes the WebSocket server, parses configuration, loads map data, and instantiates `WorldServer` instances.
   - **World Management**: [`server/js/worldserver.js`](file:///home/vijaykoushik/Evee/My%20Documents/GitHub/BrowserQuest/server/js/worldserver.js) manages player instancing across worlds, spatial entity broadcasting (zones/groups), mob spawning, item drops, and periodic world updates.
   - **Networking**: [`server/js/ws.js`](file:///home/vijaykoushik/Evee/My%20Documents/GitHub/BrowserQuest/server/js/ws.js) supports binary encoding (BSON via `bison`) and JSON messaging over WebSockets.

3. **Client Architecture**:
   - **Entrypoint**: [`client/index.html`](file:///home/vijaykoushik/Evee/My%20Documents/GitHub/BrowserQuest/client/index.html) loads styles, dependencies, and bootstrap scripts via RequireJS.
   - **Game Loop & Rendering**: [`client/js/game.js`](file:///home/vijaykoushik/Evee/My%20Documents/GitHub/BrowserQuest/client/js/game.js) and [`client/js/renderer.js`](file:///home/vijaykoushik/Evee/My%20Documents/GitHub/BrowserQuest/client/js/renderer.js) drive canvas rendering, animated sprites, camera tracking, and player input.
   - **Networking**: [`client/js/gameclient.js`](file:///home/vijaykoushik/Evee/My%20Documents/GitHub/BrowserQuest/client/js/gameclient.js) establishes the WebSocket connection to the game server, deserializes packets, and sends user actions.

---

## Common Development Workflows

### Prerequisites
- Node.js (v0.10+ / modern Node compatibility or legacy runtime tools)
- npm

### Server Setup & Running
1. Install dependencies:
   ```bash
   npm install
   ```
2. (Optional) Create a local configuration override:
   ```bash
   cp server/config_local.json-dist server/config_local.json
   ```
3. Start the game server:
   ```bash
   node server/js/main.js
   ```
4. Verify health status:
   ```bash
   curl http://localhost:8000/status
   ```

### Client Development & Build
- **Development**: Serve the [`client/`](file:///home/vijaykoushik/Evee/My%20Documents/GitHub/BrowserQuest/client/) directory using any static web server (e.g. `npx serve client` or Python's `http.server`). Ensure [`client/config/config_build.json`](file:///home/vijaykoushik/Evee/My%20Documents/GitHub/BrowserQuest/client/config/) points to your server's host and port.
- **Production Client Build**:
  ```bash
  cd bin
  chmod +x build.sh
  ./build.sh
  ```
  This creates an optimized, bundled client in `client-build/`.

### Docker Stack & Containerized Deployment
The repository includes a multi-container Docker Stack configured on unique, non-standard ports:
- **Frontend & Web Gateway**: `http://localhost:39080`
- **Game Server Backend (Direct)**: `http://localhost:39000`

Commands:
1. **Build and Run Stack**:
   ```bash
   docker compose up -d --build
   ```
2. **Check Stack Status & Health**:
   ```bash
   docker compose ps
   curl http://localhost:39080/status
   curl http://localhost:39000/status
   ```
3. **Stop Stack**:
   ```bash
   docker compose down
   ```

### Map Processing
- Map source files are authored in Tiled (`.tmx`) in [`tools/maps/tmx/`](file:///home/vijaykoushik/Evee/My%20Documents/GitHub/BrowserQuest/tools/maps/tmx/).
- Export script generates client and server map JSON files:
  ```bash
  cd tools/maps
  node exportmap.js
  ```

---

## Guidelines for AI Agents

- **Preserve Shared Protocol**: Any changes to message types, entities, items, or equipment must be kept in sync between [`shared/js/gametypes.js`](file:///home/vijaykoushik/Evee/My%20Documents/GitHub/BrowserQuest/shared/js/gametypes.js), [`server/js/`](file:///home/vijaykoushik/Evee/My%20Documents/GitHub/BrowserQuest/server/js/), and [`client/js/`](file:///home/vijaykoushik/Evee/My%20Documents/GitHub/BrowserQuest/client/js/).
- **Preserve Comments & Licenses**: Maintain license headers and author attributions when modifying files.
- **File References**: Always use clickable markdown links with `file://` URIs when referencing code or configuration files.
- **Modular AMD Architecture**: Client code uses RequireJS AMD modules (`define([...], function(...) { ... })`). Follow the existing pattern when adding or refactoring client scripts.
- **Server Entity Model**: Server entities inherit from base classes (e.g., [`server/js/entity.js`](file:///home/vijaykoushik/Evee/My%20Documents/GitHub/BrowserQuest/server/js/entity.js), [`server/js/character.js`](file:///home/vijaykoushik/Evee/My%20Documents/GitHub/BrowserQuest/server/js/character.js)). Maintain standard lifecycle callbacks and spatial broadcast patterns.
