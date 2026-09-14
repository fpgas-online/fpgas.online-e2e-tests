### welland: 14 boards, audited 2026-09-14T05:58:32Z

| board | page | camera | terminal | poe status | ssh | upload | power cycle |
|---|---|---|---|---|---|---|---|
| pi-sw2-p16 | ok | ok | ok | FAIL (not shown) | FAIL | skipped | skipped |
| pi-sw2-p29 | ok | ok | ok | FAIL (not shown) | FAIL | skipped | skipped |
| pi-sw2-p33 | ok | ok | ok | FAIL (not shown) | FAIL | skipped | skipped |
| pi-sw2-p34 | ok | ok | ok | FAIL (not shown) | FAIL | skipped | skipped |
| pi-sw2-p35 | ok | ok | ok | FAIL (not shown) | FAIL | skipped | skipped |
| pi-sw2-p36 | ok | ok | ok | FAIL (not shown) | FAIL | skipped | skipped |
| pi-sw2-p37 | ok | ok | ok | FAIL (not shown) | FAIL | skipped | skipped |
| pi-sw2-p38 | ok | ok | ok | FAIL (not shown) | FAIL | skipped | skipped |
| pi-sw2-p42 | ok | ok | ok | FAIL (not shown) | FAIL | skipped | skipped |
| pi-sw2-p43 | ok | ok | ok | FAIL (not shown) | FAIL | skipped | skipped |
| pi-sw2-p44 | ok | ok | ok | FAIL (not shown) | FAIL | skipped | skipped |
| pi-sw2-p46 | ok | ok | FAIL | FAIL (not shown) | FAIL | skipped | skipped |
| pi-sw2-p47 | ok | ok | ok | FAIL (not shown) | FAIL | skipped | skipped |
| pi-sw2-p48 | ok | ok | ok | FAIL (not shown) | FAIL | skipped | skipped |

Why:

- **pi-sw2-p16 poe status** (30s): the status box reports the PoE state after 'Check PoE': 'power' never appeared after the click; the box added: ''
- **pi-sw2-p16 ssh** (31s): `ssh -p 21622 pi@welland.fpgas.online` logs in with the banner's password: 'ssh -p 21622 pi@welland.fpgas.online' printed nothing more within 30.0s; so far: ''
- **pi-sw2-p29 poe status** (30s): the status box reports the PoE state after 'Check PoE': 'power' never appeared after the click; the box added: ''
- **pi-sw2-p29 ssh** (31s): `ssh -p 22922 pi@welland.fpgas.online` logs in with the banner's password: 'ssh -p 22922 pi@welland.fpgas.online' printed nothing more within 30.0s; so far: ''
- **pi-sw2-p33 poe status** (30s): the status box reports the PoE state after 'Check PoE': 'power' never appeared after the click; the box added: ''
- **pi-sw2-p33 ssh** (31s): `ssh -p 23322 pi@welland.fpgas.online` logs in with the banner's password: 'ssh -p 23322 pi@welland.fpgas.online' printed nothing more within 30.0s; so far: ''
- **pi-sw2-p34 poe status** (30s): the status box reports the PoE state after 'Check PoE': 'power' never appeared after the click; the box added: ''
- **pi-sw2-p34 ssh** (31s): `ssh -p 23422 pi@welland.fpgas.online` logs in with the banner's password: 'ssh -p 23422 pi@welland.fpgas.online' printed nothing more within 30.0s; so far: ''
- **pi-sw2-p35 poe status** (30s): the status box reports the PoE state after 'Check PoE': 'power' never appeared after the click; the box added: ''
- **pi-sw2-p35 ssh** (31s): `ssh -p 23522 pi@welland.fpgas.online` logs in with the banner's password: 'ssh -p 23522 pi@welland.fpgas.online' printed nothing more within 30.0s; so far: ''
- **pi-sw2-p36 poe status** (30s): the status box reports the PoE state after 'Check PoE': 'power' never appeared after the click; the box added: ''
- **pi-sw2-p36 ssh** (31s): `ssh -p 23622 pi@welland.fpgas.online` logs in with the banner's password: 'ssh -p 23622 pi@welland.fpgas.online' printed nothing more within 30.0s; so far: ''
- **pi-sw2-p37 poe status** (30s): the status box reports the PoE state after 'Check PoE': 'power' never appeared after the click; the box added: ''
- **pi-sw2-p37 ssh** (31s): `ssh -p 23722 pi@welland.fpgas.online` logs in with the banner's password: 'ssh -p 23722 pi@welland.fpgas.online' printed nothing more within 30.0s; so far: ''
- **pi-sw2-p38 poe status** (31s): the status box reports the PoE state after 'Check PoE': 'power' never appeared after the click; the box added: ''
- **pi-sw2-p38 ssh** (31s): `ssh -p 23822 pi@welland.fpgas.online` logs in with the banner's password: 'ssh -p 23822 pi@welland.fpgas.online' printed nothing more within 30.0s; so far: ''
- **pi-sw2-p42 poe status** (30s): the status box reports the PoE state after 'Check PoE': 'power' never appeared after the click; the box added: ''
- **pi-sw2-p42 ssh** (31s): `ssh -p 24222 pi@welland.fpgas.online` logs in with the banner's password: 'ssh -p 24222 pi@welland.fpgas.online' printed nothing more within 30.0s; so far: ''
- **pi-sw2-p43 poe status** (30s): the status box reports the PoE state after 'Check PoE': 'power' never appeared after the click; the box added: ''
- **pi-sw2-p43 ssh** (31s): `ssh -p 24322 pi@welland.fpgas.online` logs in with the banner's password: 'ssh -p 24322 pi@welland.fpgas.online' printed nothing more within 30.0s; so far: ''
- **pi-sw2-p44 poe status** (30s): the status box reports the PoE state after 'Check PoE': 'power' never appeared after the click; the box added: ''
- **pi-sw2-p44 ssh** (31s): `ssh -p 24422 pi@welland.fpgas.online` logs in with the banner's password: 'ssh -p 24422 pi@welland.fpgas.online' printed nothing more within 30.0s; so far: ''
- **pi-sw2-p46 terminal** (66s): the web terminal reaches a shell prompt: no shell prompt within 45.0s; the screen reads "(no terminal surface: no terminal within 1.0s; the iframe reads 'Hostname\\nPort\\nUsername\\nPassword\\nPrivate Key\\nPassphrase\\nTotp (time-based one-time password)\\nConnect Reset\\nWebsocket authentication failed.')" and the socket sent ''
- **pi-sw2-p46 poe status** (30s): the status box reports the PoE state after 'Check PoE': 'power' never appeared after the click; the box added: ''
- **pi-sw2-p46 ssh** (31s): `ssh -p 24622 pi@welland.fpgas.online` logs in with the banner's password: 'ssh -p 24622 pi@welland.fpgas.online' printed nothing more within 30.0s; so far: ''
- **pi-sw2-p47 poe status** (30s): the status box reports the PoE state after 'Check PoE': 'power' never appeared after the click; the box added: ''
- **pi-sw2-p47 ssh** (31s): `ssh -p 24722 pi@welland.fpgas.online` logs in with the banner's password: 'ssh -p 24722 pi@welland.fpgas.online' printed nothing more within 30.0s; so far: ''
- **pi-sw2-p48 poe status** (30s): the status box reports the PoE state after 'Check PoE': 'power' never appeared after the click; the box added: ''
- **pi-sw2-p48 ssh** (31s): `ssh -p 24822 pi@welland.fpgas.online` logs in with the banner's password: 'ssh -p 24822 pi@welland.fpgas.online' printed nothing more within 30.0s; so far: ''

Seen:

- pi-sw2-p16 page (0s): heading reads 'Accessing pi-sw2-p16 — Digilent Arty A7-35T'; heading reads 'Accessing pi-sw2-p16 — Digilent Arty A7-35T'; the index said 'Digilent Arty A7-35T'
- pi-sw2-p16 camera (8s): clock '06:38:58' -> '06:39:01' (clock pixels moved 0.67%, 2.29%)
- pi-sw2-p16 terminal (10s): 'pi-sw2-p16' seen in all three readings; output lines ['pi-sw2-p16']; 'up' seen in all three readings
- pi-sw2-p29 page (0s): heading reads 'Accessing pi-sw2-p29 — Sqrl Acorn CLE-215+'; heading reads 'Accessing pi-sw2-p29 — Sqrl Acorn CLE-215+'; the index said 'Sqrl Acorn CLE-215+'
- pi-sw2-p29 camera (8s): clock '06:40:17' -> '06:40:21' (clock pixels moved 0.84%, 1.67%)
- pi-sw2-p29 terminal (8s): 'pi-sw2-p29' seen in all three readings; output lines ['pi-sw2-p29']; 'up' seen in all three readings
- pi-sw2-p33 page (0s): heading reads 'Accessing pi-sw2-p33 — TT FPGA emulation (iCE40UP5K)'; heading reads 'Accessing pi-sw2-p33 — TT FPGA emulation (iCE40UP5K)'; the index said 'TT FPGA emulation (iCE40UP5K)'
- pi-sw2-p33 camera (8s): clock None -> None (clock pixels moved 0.82%, 1.76%)
- pi-sw2-p33 terminal (8s): 'pi-sw2-p33' seen in all three readings; output lines ['pi-sw2-p33']; 'up' seen in all three readings
- pi-sw2-p34 page (0s): heading reads 'Accessing pi-sw2-p34 — TT FPGA emulation (iCE40UP5K)'; heading reads 'Accessing pi-sw2-p34 — TT FPGA emulation (iCE40UP5K)'; the index said 'TT FPGA emulation (iCE40UP5K)'
- pi-sw2-p34 camera (8s): clock '06:42:56' -> '06:42:59' (clock pixels moved 0.92%, 0.77%)
- pi-sw2-p34 terminal (10s): 'pi-sw2-p34' seen in all three readings; output lines ['pi-sw2-p34']; 'up' seen in all three readings
- pi-sw2-p35 page (0s): heading reads 'Accessing pi-sw2-p35 — TT FPGA emulation (iCE40UP5K)'; heading reads 'Accessing pi-sw2-p35 — TT FPGA emulation (iCE40UP5K)'; the index said 'TT FPGA emulation (iCE40UP5K)'
- pi-sw2-p35 camera (9s): clock None -> '6:44:21' (clock pixels moved 0.86%, 1.82%)
- pi-sw2-p35 terminal (11s): 'pi-sw2-p35' seen in all three readings; output lines ['pi-sw2-p35']; 'up' seen in all three readings
- pi-sw2-p36 page (0s): heading reads 'Accessing pi-sw2-p36 — TT FPGA emulation (iCE40UP5K)'; heading reads 'Accessing pi-sw2-p36 — TT FPGA emulation (iCE40UP5K)'; the index said 'TT FPGA emulation (iCE40UP5K)'
- pi-sw2-p36 camera (8s): clock None -> None (clock pixels moved 1.67%, 1.00%)
- pi-sw2-p36 terminal (8s): 'pi-sw2-p36' seen in all three readings; output lines ['pi-sw2-p36']; 'up' seen in all three readings
- pi-sw2-p37 page (0s): heading reads 'Accessing pi-sw2-p37 — Digilent Arty A7-35T'; heading reads 'Accessing pi-sw2-p37 — Digilent Arty A7-35T'; the index said 'Digilent Arty A7-35T'
- pi-sw2-p37 camera (8s): clock None -> None (clock pixels moved 2.56%, 1.07%)
- pi-sw2-p37 terminal (8s): 'pi-sw2-p37' seen in all three readings; output lines ['pi-sw2-p37']; 'up' seen in all three readings
- pi-sw2-p38 page (0s): heading reads 'Accessing pi-sw2-p38 — Digilent Arty A7-35T'; heading reads 'Accessing pi-sw2-p38 — Digilent Arty A7-35T'; the index said 'Digilent Arty A7-35T'
- pi-sw2-p38 camera (8s): clock '06:48:17' -> '06:48:21' (clock pixels moved 0.80%, 1.47%)
- pi-sw2-p38 terminal (10s): 'pi-sw2-p38' seen in all three readings; output lines ['pi-sw2-p38']; 'up' seen in all three readings
- pi-sw2-p42 page (0s): heading reads 'Accessing pi-sw2-p42 — Digilent Arty A7-35T'; heading reads 'Accessing pi-sw2-p42 — Digilent Arty A7-35T'; the index said 'Digilent Arty A7-35T'
- pi-sw2-p42 camera (8s): clock '06:49:39' -> '06:49:42' (clock pixels moved 1.76%, 0.62%)
- pi-sw2-p42 terminal (10s): 'pi-sw2-p42' seen in all three readings; output lines ['pi-sw2-p42']; 'up' seen in all three readings
- pi-sw2-p43 page (0s): heading reads 'Accessing pi-sw2-p43 — Sqrl Acorn CLE-215+'; heading reads 'Accessing pi-sw2-p43 — Sqrl Acorn CLE-215+'; the index said 'Sqrl Acorn CLE-215+'
- pi-sw2-p43 camera (8s): clock '06:50:59' -> '06:51:02' (clock pixels moved 2.29%, 1.07%)
- pi-sw2-p43 terminal (8s): 'pi-sw2-p43' seen in all three readings; output lines ['pi-sw2-p43']; 'up' seen in all three readings
- pi-sw2-p44 page (0s): heading reads 'Accessing pi-sw2-p44 — Sqrl Acorn CLE-215+'; heading reads 'Accessing pi-sw2-p44 — Sqrl Acorn CLE-215+'; the index said 'Sqrl Acorn CLE-215+'
- pi-sw2-p44 camera (8s): clock '6:52:17' -> '06:52:20' (clock pixels moved 0.83%, 1.27%)
- pi-sw2-p44 terminal (8s): 'pi-sw2-p44' seen in all three readings; output lines ['pi-sw2-p44']; 'up' seen in all three readings
- pi-sw2-p46 page (0s): heading reads 'Accessing pi-sw2-p46 — Sqrl Acorn CLE-215+'; heading reads 'Accessing pi-sw2-p46 — Sqrl Acorn CLE-215+'; the index said 'Sqrl Acorn CLE-215+'
- pi-sw2-p46 camera (8s): clock '06:53:36' -> None (clock pixels moved 0.63%, 0.62%)
- pi-sw2-p47 page (0s): heading reads 'Accessing pi-sw2-p47 — Sqrl Acorn CLE-215+'; heading reads 'Accessing pi-sw2-p47 — Sqrl Acorn CLE-215+'; the index said 'Sqrl Acorn CLE-215+'
- pi-sw2-p47 camera (8s): clock '06:55:52' -> '06:55:56' (clock pixels moved 0.90%, 1.00%)
- pi-sw2-p47 terminal (8s): 'pi-sw2-p47' seen in all three readings; output lines ['pi-sw2-p47']; 'up' seen in all three readings
- pi-sw2-p48 page (0s): heading reads 'Accessing pi-sw2-p48 — Sqrl Acorn CLE-215+'; heading reads 'Accessing pi-sw2-p48 — Sqrl Acorn CLE-215+'; the index said 'Sqrl Acorn CLE-215+'
- pi-sw2-p48 camera (8s): clock '6:57:11' -> '06:57:14' (clock pixels moved 0.72%, 1.09%)
- pi-sw2-p48 terminal (10s): 'pi-sw2-p48' seen in all three readings; output lines ['pi-sw2-p48']; 'up' seen in all three readings
