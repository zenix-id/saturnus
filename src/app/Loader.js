import { loadCorePlugins } from './plugins/coreLoader.js';  // Import the core plugin loader
import { loadDbPlugins } from './plugins/dbLoader.js';  // Import the database plugin loader

// Function to register plugins
export const registerPlugins = async (fastify) => {
  // await loadDbPlugins(fastify);   // Register the database plugins
  await loadCorePlugins(fastify); // Register the core plugins
};
