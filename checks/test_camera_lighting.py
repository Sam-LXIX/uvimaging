"""Execute the actual C lighting functions/command branch with mocked LEDC calls.

This host check is not a replacement for an ESP-IDF build or hardware testing.
"""
import ast
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
C=(ROOT/'firmware/LOTUS_ESP32S3_8MB/main/main.c').read_text()

def function(name):
    start=C.index('static bool '+name+'(')
    opening=C.index('{',start);depth=1;end=opening+1
    while depth:
        depth+=(C[end]=='{')-(C[end]=='}');end+=1
    return C[start:end]

class LightingTests(unittest.TestCase):
    def test_ui_keeps_uv_independent(self):
        tree=ast.parse((ROOT/'LOTUS_UI_Cladding.py').read_text())
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='LotusUI')
        method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='setting_choices')
        choices=ast.literal_eval(method.body[0].value)
        self.assertEqual(choices['Camera lighting'],('Off','12.5%','25%','50%'))
        self.assertEqual(choices['UV intensity'],('25%','50%','75%','100%'))

    @unittest.skipUnless(shutil.which('gcc'),'host gcc required')
    def test_pwm_and_command_errors(self):
        branch=C[C.index('    float light_percent = 0.0f;'):C.index('    int arm = 0;')]
        prelude=r'''
#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include <math.h>
#include <assert.h>
typedef int ledc_channel_t;
typedef int esp_err_t;
#define ESP_OK 0
#define PWM_MAX 1023
#define PWM_MODE 0
#define PWM_CH_LIGHT 2
#define CAMERA_LIGHT_MAX_PERCENT 50.0f
static float g_light_percent;
static int fail_set,fail_update,updates;
static uint32_t duty;
static int ledc_set_duty(int mode,int channel,uint32_t value) {
    (void)mode; assert(channel==PWM_CH_LIGHT); duty=value; return fail_set;
}
static int ledc_update_duty(int mode,int channel) {
    (void)mode; assert(channel==PWM_CH_LIGHT); updates++; return fail_update;
}
static void state_lock(void) {}
static void state_unlock(void) {}
'''
        main=r'''
int main(void) {
    assert(set_light_percent(12.5f)); assert(duty==128); assert(g_light_percent==12.5f);
    assert(set_light_percent(100)); assert(duty==512); assert(g_light_percent==50);
    assert(set_light_percent(NAN)); assert(duty==0);
    assert(set_light_percent(12.5f));
    fail_set=1; int old_updates=updates;
    assert(!set_light_percent(25)); assert(g_light_percent==12.5f); assert(updates==old_updates);
    fail_set=0; fail_update=1;
    command("LIGHT 25"); assert(g_light_percent==12.5f);
    fail_update=0;
    command("LIGHT 12.5"); command("LIGHT 50");
    command("LIGHT 51"); command("LIGHT nan"); command("LIGHT -1");
    command("LIGHT 12.5junk"); command("LIGHT 12.5 extra"); command("LIGHT nope");
    assert(g_light_percent==50);
    return 0;
}
'''
        source=prelude+function('pwm_set_camera_light_percent')+function('set_light_percent')+'\nstatic void command(const char *line) {\n'+branch+'}\n'+main
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory);(path/'test.c').write_text(source)
            subprocess.run(['gcc','-std=c11','-Wall','-Wextra','-Werror',str(path/'test.c'),'-lm','-o',str(path/'test')],check=True,capture_output=True)
            output=subprocess.check_output([str(path/'test')],text=True).splitlines()
        self.assertEqual(output,['ERR LIGHT pwm_failed','OK LIGHT percent=12.5','OK LIGHT percent=50.0',
            'ERR LIGHT range_max_50','ERR LIGHT range_max_50','ERR LIGHT range_max_50',
            'ERR LIGHT syntax','ERR LIGHT syntax','ERR LIGHT syntax'])

    def test_version_consistency(self):
        for name in ('main/main.c','CMakeLists.txt','flash_firmware.py','README.txt'):
            self.assertIn('1.2.5-s3-8mb',(ROOT/'firmware/LOTUS_ESP32S3_8MB'/name).read_text())

if __name__=='__main__':unittest.main()
