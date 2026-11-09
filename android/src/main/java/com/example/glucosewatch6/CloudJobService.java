package com.example.glucosewatch6;

import android.app.job.*;
import android.content.ComponentName;
import android.content.Context;

public final class CloudJobService extends JobService {
    static void schedule(Context c) {
        if (!CloudConfig.configured(c)) return;
        JobScheduler scheduler=c.getSystemService(JobScheduler.class);
        if (scheduler.getPendingJob(62020)!=null) return;
        scheduler.schedule(new JobInfo.Builder(62020,new ComponentName(c,CloudJobService.class))
            .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY).setPeriodic(900000).setPersisted(true).build());
    }
    @Override public boolean onStartJob(JobParameters params) {
        CloudSync.job(this,()->jobFinished(params,false));return true;
    }
    @Override public boolean onStopJob(JobParameters params) { return true; }
}
