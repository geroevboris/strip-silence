import sys, os, wave, tempfile, math, struct, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from audio import WavFile

class TestAudio(unittest.TestCase):
    def test_pcm16two_islands(self):
        sr=48000; length=round(sr*2.0)
        with tempfile.TemporaryDirectory() as d:
            src=os.path.join(d,'test.wav'); dst=os.path.join(d,'piece.wav')
            with wave.open(src,'wb') as f:
                f.setnchannels(2); f.setsampwidth(2); f.setframerate(sr)
                block=bytearray()
                for i in range(length):
                    t=i/sr
                    a=int(18000*math.sin(2*math.pi*440*t)) if 0.2<=t<=0.6 or 1.2<=t<=1.65 else 0
                    block += struct.pack('<hh',a,a)
                f.writeframes(block)
            audio=WavFile(src)
            self.assertEqual((audio.rate,audio.bits,audio.frames),(48000,16,96000))
            spans=audio.detect(0,2,-45,200,20)
            self.assertEqual(len(spans),2, spans)
            self.assertTrue(0.17 < spans[0][0]/sr < .21)
            self.assertTrue(1.17 < spans[1][0]/sr < 1.21)
            audio.write_slice(*spans[0],dst)
            out=WavFile(dst)
            self.assertEqual(out.frames,spans[0][1]-spans[0][0])
            with open(src,'rb') as f,open(dst,'rb') as g:
                f.seek(audio.data_offset+spans[0][0]*audio.align); g.seek(out.data_offset)
                self.assertEqual(f.read(out.frames*out.align),g.read(out.frames*out.align))

    def test_float32(self):
        with tempfile.TemporaryDirectory() as d:
            path=os.path.join(d,'float.wav')
            rate=48000; length=rate
            vals=[0.25*math.sin(i*0.4) if 10000<i<15000 or 30000<i<40000 else 0 for i in range(length)]
            payload=struct.pack('<%df'%len(vals),*vals)
            fmt=struct.pack('<HHIIHH',3,1,rate,rate*4,4,32)
            riff=4+(8+16)+(8+len(payload))
            with open(path,'wb') as f:
                f.write(b'RIFF'+struct.pack('<I',riff)+b'WAVEfmt '+struct.pack('<I',len(fmt))+fmt+b'data'+struct.pack('<I',len(payload))+payload)
            w=WavFile(path)
            spans=w.detect(0,1,-40,150,10)
            self.assertEqual(len(spans),2)
            out=os.path.join(d,'out.wav');w.write_slice(*spans[0],out)
            self.assertEqual(WavFile(out).tag,3)

    def test_stay_within_clip(self):
        sr=44100
        with tempfile.TemporaryDirectory() as d:
            path=os.path.join(d,'short.wav')
            with wave.open(path,'wb') as f:
                f.setnchannels(1);f.setsampwidth(2);f.setframerate(sr)
                f.writeframes(struct.pack('<h',8000)*sr)
            wav=WavFile(path)
            self.assertEqual(len(wav.detect(.1,.2,-30,150,0)),1)
            with self.assertRaises(ValueError): wav.detect(.95,.3,-30,150,0)

if __name__=='__main__':unittest.main()


class TestWaveformUI(unittest.TestCase):
    def test_waveform_has_bounded_samples(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'sample.wav')
            rate = 24000
            with wave.open(path, 'wb') as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(rate)
                samples = [18000 if rate // 2 <= i < rate else 0 for i in range(rate * 2)]
                w.writeframes(struct.pack('<%dh' % len(samples), *samples))
            result = WavFile(path).envelope(0, 2, 256)
            self.assertEqual(len(result), 256)
            self.assertAlmostEqual(max(result[:50]), 0.)
            self.assertGreater(max(result[80:120]), .4)
            self.assertAlmostEqual(max(result[160:]), 0.)
