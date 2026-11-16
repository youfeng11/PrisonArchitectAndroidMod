package com.youfeng.pa.tools.platform.gameobb;

import android.os.ParcelFileDescriptor;

interface IObbInstaller {
    void install(in ParcelFileDescriptor archive, long length) = 0;
    void restore() = 1;
    ParcelFileDescriptor openGameObb() = 2;
}
