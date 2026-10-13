const path=require('node:path');
const os=require('node:os');

try {
  module.exports=require('playwright');
}catch(error){
  if(error.code!=='MODULE_NOT_FOUND')throw error;
  const runtime=process.env.FITGATE_PLAYWRIGHT_MODULE || path.join(os.homedir(),'.cache','codex-runtimes','codex-primary-runtime','dependencies','node','node_modules','playwright');
  module.exports=require(runtime);
}
