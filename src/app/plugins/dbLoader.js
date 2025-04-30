import AutoLoad from '@fastify/autoload';
import path from 'path';

// Function to register DB plugins via AutoLoad
export const loadDbPlugins = (fastify) => {
  const pluginDir = resolvePluginDirectory();
  console.log('Plugin Directory Path:', pluginDir);

  fastify.register(AutoLoad, {
    dir: pluginDir,  // Path to the plugins directory
    options: {},      // Pass any options to the plugins if needed
  });
};

// Function to resolve the path to the plugin directory
const resolvePluginDirectory = () => {
  // Use import.meta.url to resolve the __dirname equivalent
  const __dirname = path.dirname(new URL(import.meta.url).pathname);
  return path.join(__dirname, 'db');  // Resolves to the './db' directory relative to the current file
};
