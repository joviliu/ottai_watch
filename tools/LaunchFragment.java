// Adapted from oryonatan/xiaomi-band-development, MIT; see THIRD_PARTY_NOTICES.txt.
import android.content.Intent;
import android.os.Looper;
import android.os.Parcelable;
import java.lang.reflect.Method;

public class LaunchFragment {
    public static void main(String[] args) {
        try {
            Looper.prepareMainLooper();
            dalvik.system.PathClassLoader loader = new dalvik.system.PathClassLoader(args[0], ClassLoader.getSystemClassLoader());
            Class<?> builderClass = loader.loadClass("com.xiaomi.fitness.baseui.common.FragmentParams$b");
            Object builder = builderClass.getDeclaredConstructor().newInstance();
            Class<?> fragment = loader.loadClass("com.xiaomi.xms.wearable.ui.debug.ThirdAppDebugFragment");
            Method setter = null, build = null;
            for (Method method : builderClass.getDeclaredMethods()) {
                if (method.getParameterTypes().length == 1 && method.getParameterTypes()[0] == Class.class) setter = method;
                if (method.getParameterTypes().length == 0 && method.getReturnType().getName().equals("com.xiaomi.fitness.baseui.common.FragmentParams")) build = method;
            }
            if (setter == null || build == null) {
                for (Method method : builderClass.getDeclaredMethods()) System.err.println(method);
                throw new IllegalStateException("Unsupported FragmentParams builder");
            }
            setter.setAccessible(true); setter.invoke(builder, fragment);
            build.setAccessible(true); Object params = build.invoke(builder);
            Intent intent = new Intent().setClassName("com.xiaomi.wearable", "com.xiaomi.fitness.baseui.common.CommonBaseActivity");
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TASK);
            intent.putExtra("fragment_param", (Parcelable)params);
            Method getService = Class.forName("android.app.ActivityManager").getDeclaredMethod("getService");
            getService.setAccessible(true); Object manager = getService.invoke(null);
            for (Method method : manager.getClass().getMethods()) {
                if (!method.getName().equals("startActivity")) continue;
                Class<?>[] types = method.getParameterTypes();
                boolean hasIntent = false;
                for (Class<?> type : types) if (type == Intent.class) hasIntent = true;
                if (!hasIntent || (types.length != 10 && types.length != 11)) continue;
                Object[] values = new Object[types.length];
                for (int i=0; i<types.length; i++) {
                    if (types[i] == int.class) values[i] = 0;
                    else if (types[i] == Intent.class) values[i] = intent;
                    else if (i == 1 && types[i] == String.class) values[i] = "com.android.shell";
                }
                Object result = method.invoke(manager, values);
                if (result instanceof Integer && ((Integer)result) < 0) throw new IllegalStateException("startActivity returned " + result);
                System.out.println("SUCCESS: debug activity launch requested (" + result + ")");
                return;
            }
            throw new IllegalStateException("Unsupported startActivity method");
        } catch (Throwable e) {
            System.err.println("ERROR: " + e); e.printStackTrace(); System.exit(1);
        }
    }
}
