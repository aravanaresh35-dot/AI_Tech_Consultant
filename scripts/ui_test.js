const {JSDOM}=require('jsdom');const fs=require('fs');
const ROOT=require('path').resolve(__dirname,'..'); // needs: npm i jsdom; services running
const html=fs.readFileSync(ROOT+'/frontend/src/index.html','utf8');
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 const dom=new JSDOM(html,{url:'http://localhost:8080/',runScripts:'dangerously',pretendToBeVisual:true,
  beforeParse(w){w.fetch=(u,o)=>fetch(u,o)}});
 const w=dom.window,d=w.document;const errs=[];w.addEventListener('error',e=>errs.push(e.message));
 const ok=(n,c)=>{console.log((c?'PASS ':'FAIL ')+n);if(!c)process.exitCode=1};
 const click=el=>el.dispatchEvent(new w.MouseEvent('click',{bubbles:true}));
 const tab=k=>click(d.querySelector(`nav button[data-t=${k}]`));
 await sleep(1500);ok('overview shows 3 services up',(d.getElementById('health').textContent.match(/● up/g)||[]).length===3);
 ok('demo banner visible',/DEMO/.test(d.getElementById('modes').textContent));
 tab('kb');await sleep(800);ok('articles listed',d.querySelectorAll('#arts tr').length>5);
 d.getElementById('q').value='How do I enable the member login page?';click(d.getElementById('askBtn'));await sleep(1200);
 ok('chat shows sources',/member login page/i.test(d.getElementById('ans').textContent)&&d.querySelectorAll('#ans a').length>0);
 d.getElementById('q').value='What is the warranty on drones?';click(d.getElementById('askBtn'));await sleep(1200);
 ok('unknown -> task created & listed',/task #\d+ created/.test(d.getElementById('ans').textContent)&&d.querySelectorAll('#tasks textarea').length>0);
 const ta=d.querySelector('#tasks textarea');ta.value='Drones are not a product we sell.';click(d.querySelector('#tasks button'));await sleep(1200);
 d.getElementById('q').value='What is the warranty on drones?';click(d.getElementById('askBtn'));await sleep(1200);
 ok('expert answer becomes retrievable',/not a product we sell/i.test(d.getElementById('ans').textContent));
 tab('inbox');await sleep(500);
 d.getElementById('en').value='Ana';d.getElementById('ee').value='ana@example.com';d.getElementById('es').value='Login';d.getElementById('eb').value='How do I enable the member login page?';
 click(d.getElementById('addEmail'));await sleep(2000);
 ok('draft editor shown with evidence',d.getElementById('dr')&&d.getElementById('dr').value.length>20&&/evidence/i.test(d.getElementById('edit').textContent));
 d.getElementById('dr').value+=' (edited by reviewer)';click(d.querySelector('#edit [data-a=approve]'));await sleep(1500);
 ok('approve recorded in feedback history',/approved_edited/.test(d.getElementById('fb').textContent));
 tab('meet');await sleep(500);
 d.getElementById('mt').value='UI test';d.getElementById('mc').value='UI Co';d.getElementById('mx').value=fs.readFileSync(ROOT+'/task3-meeting-to-sow/sample_transcripts/01_website_improvement.txt','utf8');
 click(d.getElementById('mkMeet'));await sleep(2500);
 ok('scope, estimate, proposal rendered',/Scope of Work/.test(d.getElementById('mview').textContent)&&/Developer estimate/.test(d.getElementById('mview').textContent)&&/Client proposal/.test(d.getElementById('mview').textContent));
 d.getElementById('fu').value=fs.readFileSync(ROOT+'/task3-meeting-to-sow/sample_transcripts/03_follow_up_changes.txt','utf8');click(d.getElementById('fuBtn'));await sleep(2500);
 ok('follow-up comparison rendered',/Changes: v1 → v2/.test(d.getElementById('mview').textContent));
 click(d.getElementById('apBtn'));await sleep(1500);
 ok('approval shows NOT sent to client',/NOT sent to client/.test(d.getElementById('mview').textContent));
 ok('no uncaught JS errors',errs.length===0);if(errs.length)console.log(errs);
 process.exit(process.exitCode||0);
})();
