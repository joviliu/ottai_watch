package com.example.glucosewatch6;

import java.util.Calendar;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class Reading {
    private static final Pattern VALUE = Pattern.compile("(?<![\\d.,+\\-])(\\d{1,2}(?:[.,]\\d{1,2})?)\\s*mmol/[lL]\\b");
    private static final Pattern TIME = Pattern.compile("更新时间\\s*[：:]\\s*(\\d{1,2}):(\\d{2})");
    private static final Pattern ARROW = Pattern.compile("[↑↗→↘↓⇈⇊]+|[↟↡]");
    public final double mmol;
    public final long sourceAt;
    public final String trend;

    public Reading(double mmol, long sourceAt, String trend) {
        this.mmol = mmol;
        this.sourceAt = sourceAt;
        this.trend = trend;
    }

    public static boolean validValue(double value) {
        return Double.isFinite(value) && value > 0 && value <= 60;
    }

    public static Reading parseOttai(String text, long notificationAt, long now) {
        if (text == null || notificationAt <= 0 || notificationAt > now + 90000) return null;
        Matcher value = VALUE.matcher(text), time = TIME.matcher(text);
        if (!value.find() || !time.find()) return null;
        double mmol = Double.parseDouble(value.group(1).replace(',', '.'));
        if (!validValue(mmol) || value.find()) return null;
        int hour = Integer.parseInt(time.group(1)), minute = Integer.parseInt(time.group(2));
        if (hour > 23 || minute > 59) return null;
        Calendar calendar = Calendar.getInstance();
        calendar.setTimeInMillis(notificationAt);
        calendar.set(Calendar.HOUR_OF_DAY, hour);
        calendar.set(Calendar.MINUTE, minute);
        calendar.set(Calendar.SECOND, 0);
        calendar.set(Calendar.MILLISECOND, 0);
        if (calendar.getTimeInMillis() > notificationAt + 90000) calendar.add(Calendar.DATE, -1);
        long sourceAt = calendar.getTimeInMillis();
        if (sourceAt > now + 90000) return null;
        Matcher arrow = ARROW.matcher(text);
        return new Reading(mmol, sourceAt, arrow.find() ? arrow.group() : "?");
    }

}
