package com.example.glucosewatch6;

import android.app.Activity;
import android.content.Context;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.RippleDrawable;
import android.view.View;
import android.widget.*;

/** Shared with the native settings page; no theme or UI library dependency. */
final class MobileStyle {
    static final int INK=0xff29364f, MUTED=0xff6e7a96, BLUE=0xff2e6ee0, VIOLET=0xff7a5fbd;
    static int dp(Context c,float n) { return Math.round(n*c.getResources().getDisplayMetrics().density); }
    static LinearLayout column(Context c) { LinearLayout v=new LinearLayout(c);v.setOrientation(LinearLayout.VERTICAL);return v; }
    static GradientDrawable rounded(Context c,int color,int radius) {
        GradientDrawable d=new GradientDrawable();d.setColor(color);d.setCornerRadius(dp(c,radius));return d;
    }
    static LinearLayout page(Activity activity) {
        activity.getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR|View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
        activity.getWindow().setStatusBarColor(Color.TRANSPARENT);activity.getWindow().setNavigationBarColor(0xfff9f6fe);
        LinearLayout page=column(activity);int pad=dp(activity,20);page.setPadding(pad,dp(activity,22),pad,dp(activity,28));
        ScrollView scroll=new ScrollView(activity);scroll.setFillViewport(true);scroll.setClipToPadding(false);
        scroll.setBackground(new GradientDrawable(GradientDrawable.Orientation.TL_BR,new int[]{0xffe8f5ff,0xfff2edff,0xfffff1e8}));
        scroll.setOnApplyWindowInsetsListener((view,insets)-> {
            view.setPadding(insets.getSystemWindowInsetLeft(),insets.getSystemWindowInsetTop(),insets.getSystemWindowInsetRight(),insets.getSystemWindowInsetBottom());
            return insets.consumeSystemWindowInsets();
        });
        scroll.addView(page);activity.setContentView(scroll);scroll.requestApplyInsets();return page;
    }
    static LinearLayout card(LinearLayout parent) {
        Context c=parent.getContext();LinearLayout card=column(c);int p=dp(c,18);card.setPadding(p,p,p,p);
        card.setBackground(rounded(c,0xfaffffff,24));
        LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(-1,-2);params.bottomMargin=dp(c,14);parent.addView(card,params);return card;
    }
    static TextView text(LinearLayout parent,String value,int size,int color,boolean medium) {
        Context c=parent.getContext();TextView t=new TextView(c);t.setText(value);t.setTextSize(size);t.setTextColor(color);
        t.setTypeface(Typeface.create(medium?"sans-serif-medium":"sans-serif",Typeface.NORMAL));
        t.setLineSpacing(dp(c,3),1);t.setPadding(0,dp(c,4),0,dp(c,6));parent.addView(t);return t;
    }
    static Button button(LinearLayout parent,String label,Runnable action) {
        Context c=parent.getContext();Button b=new Button(c);b.setText(label);b.setTextSize(15);b.setAllCaps(false);b.setTextColor(BLUE);
        b.setTypeface(Typeface.create("sans-serif-medium",Typeface.NORMAL));b.setMinHeight(dp(c,48));b.setMinimumHeight(dp(c,48));
        b.setPadding(dp(c,14),dp(c,10),dp(c,14),dp(c,10));
        b.setBackground(new RippleDrawable(ColorStateList.valueOf(0x203f78ee),rounded(c,0xffeef4ff,15),null));
        LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.topMargin=dp(c,8);parent.addView(b,p);
        b.setOnClickListener(v->action.run());return b;
    }
    static void field(EditText field) {
        Context c=field.getContext();field.setTextSize(15);field.setTextColor(INK);field.setHintTextColor(MUTED);
        int p=dp(c,13);field.setPadding(p,p,p,p);field.setBackground(rounded(c,0xfff2f5fb,13));
        LinearLayout.LayoutParams params=new LinearLayout.LayoutParams(-1,-2);params.topMargin=dp(c,10);field.setLayoutParams(params);
    }
    private MobileStyle() { }
}
