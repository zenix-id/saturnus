import AutoLoad from '@fastify/autoload';
import path from 'path';
import { fileURLToPath } from 'url'; // <-- Tambahkan import ini

// Function to register Core plugins via AutoLoad
export const loadCorePlugins = (fastify) => {
  const pluginDir = resolvePluginDirectory();
  console.log('Plugin Directory Path:', pluginDir); // Verifikasi path ini di log Anda

  // Pastikan direktori benar-benar ada sebelum mencoba mendaftarkannya
  // (Ini opsional tetapi bagus untuk debugging)
  try {
    // Coba baca direktori untuk memastikan itu ada
    // Anda mungkin perlu mengimpor 'fs' jika Anda menggunakan ini: import fs from 'fs/promises';
    // await fs.readdir(pluginDir); 
    console.log(`Directory ${pluginDir} seems accessible.`); 
  } catch (err) {
    console.error(`Error accessing plugin directory ${pluginDir}:`, err);
    // Mungkin lempar error atau tangani agar aplikasi tidak crash saat startup
    // throw new Error(`Plugin directory not found or accessible: ${pluginDir}`);
  }

  fastify.register(AutoLoad, {
    dir: pluginDir,  // Path to the plugins directory
    options: {},      // Pass any options to the plugins if needed
    // Tambahkan opsi lain jika perlu, mis. ignorePattern, etc.
  });
};

// Function to resolve the path to the plugin directory
const resolvePluginDirectory = () => {
  // Cara yang benar untuk mendapatkan __dirname di ES Modules
  const __filename = fileURLToPath(import.meta.url);
  const __dirname = path.dirname(__filename);

  // Menggunakan path.resolve untuk mendapatkan path absolut yang dijamin
  // Ini akan menggabungkan __dirname dengan 'core'
  // Contoh: Jika __dirname adalah 'X:\REPO\saturnus\api\app\plugins', hasilnya akan 'X:\REPO\saturnus\api\app\plugins\core'
  return path.resolve(__dirname, 'core');
};