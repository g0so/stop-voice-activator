import sys,ctypes,json,wave
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path('outputs').resolve()))
import tensorflow as tf
from audio_features import features
lib=ctypes.CDLL(str(Path('work/frontend_check.so').resolve()))
lib.centered_features.argtypes=[ctypes.POINTER(ctypes.c_int16),ctypes.POINTER(ctypes.c_float),ctypes.c_uint]
rt=tf.lite.Interpreter(model_path=sys.argv[1] if len(sys.argv)>1 else 'outputs/stop_model_reviewed_v10/stop_int8.tflite',num_threads=1,experimental_op_resolver_type=tf.lite.experimental.OpResolverType.BUILTIN_REF);rt.allocate_tensors()
inp=rt.get_input_details()[0];scale,zero=inp['quantization']
manifest=json.loads(Path('outputs/reviewed_restart_manifest.json').read_text());maxfloat=0.;maxq=0;different=0;count=0;maxout=0
for r in manifest['recordings']['train']+manifest['recordings']['validation']:
 with wave.open(r['wav']) as w:a=np.frombuffer(w.readframes(w.getnframes()),dtype='<i2')
 for offset in [0,16000,32000,64000]:
  pcm=np.ascontiguousarray(a[offset:offset+16000]);cpp=np.zeros((49,24,1),np.float32)
  first=(count*13)%49
  lib.centered_features(pcm.ctypes.data_as(ctypes.POINTER(ctypes.c_int16)),cpp.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),first)
  py=features(pcm.astype(np.float32)/32768);py-=py.mean(axis=0,keepdims=True)
  maxfloat=max(maxfloat,float(abs(cpp-py).max()))
  quant=lambda x:np.clip(np.rint(x/scale)+zero,-128,127).astype(np.int8)
  qc,qp=quant(cpp),quant(py);d=abs(qc.astype(int)-qp.astype(int));maxq=max(maxq,int(d.max()));different+=int(np.sum(d!=0));count+=1
  out=[]
  for q in [qc,qp]:
   rt.set_tensor(inp['index'],q[None]);rt.invoke();out.append(rt.get_tensor(rt.get_output_details()[0]['index']).astype(int))
  maxout=max(maxout,int(abs(out[0]-out[1]).max()))
result={'windows':count,'features_compared':count*1176,'max_float_difference':maxfloat,'max_quantized_input_difference':maxq,'different_quantized_inputs':different,'max_model_output_difference':maxout,'scope':'Actual C++ frontend and shared centering helper on host versus Python; rotating ring order covered. MCU numerical parity still requires board self-test.'}
assert maxfloat<2e-5 and maxq<=1 and maxout<=3,result
Path('work/frontend_parity_latest.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
