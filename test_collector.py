import unittest, tempfile, json
from pathlib import Path
import collector as s
class WatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); s.DB=Path(self.tmp.name)/'test.sqlite3'; s.init()
    def tearDown(self): self.tmp.cleanup()
    def test_rss_and_duplicate_actions(self):
        raw=b'''<rss><channel><item><title>Test only</title><description>Fixture</description><link>https://www.whitehouse.gov/presidential-actions/test/</link><pubDate>Thu, 26 Nov 2026 01:00:00 GMT</pubDate></item></channel></rss>'''
        s.save('whitehouse',s.parse_rss(raw,'whitehouse')); s.save('actions',s.parse_rss(raw,'actions'))
        with s.conn() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM items').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT kind FROM items').fetchone()[0],'order')
            self.assertEqual(c.execute('SELECT count(*) FROM status').fetchone()[0],2)
    def test_cnn_and_dedup(self):
        data=[{'id':'test','url':'https://truthsocial.com/@realDonaldTrump/test','created_at':'2026-11-26T01:00:00Z','content':'<p>Fixture only</p>'}]
        items=s.parse_cnn(json.dumps(data)); s.save('trump_cnn',items); s.save('trump_cnn',items)
        with s.conn() as c: self.assertEqual(c.execute('SELECT count(*) FROM items').fetchone()[0],1)
    def test_failure_preserves_data(self):
        s.save('trump',[]); s.fail('trump','fixture failure')
        with s.conn() as c:
            row=c.execute('SELECT * FROM status').fetchone(); self.assertTrue(row['success']); self.assertEqual(row['error'],'fixture failure')
    def test_bad_feed(self):
        with self.assertRaises(ValueError): s.parse_cnn(b'{}')
        with self.assertRaises(ValueError): s.parse_rss(b'<html/>','trump')
if __name__=='__main__': unittest.main()
