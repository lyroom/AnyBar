#include <windows.h>
#include <ole2.h>
#include <uiautomation.h>
#include <stdlib.h>

#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "oleaut32.lib")

extern "C" {

/**
 * 查询任务栏内运行图标的最右侧边缘坐标（毫秒级原生 UIA 实现，0 额外子进程）
 * @param tray_left_phys Python 传入的物理托盘左边缘坐标
 * @param rebar_right_phys Python 传入的物理 ReBar 右边缘坐标
 * @return 换算后的图标最右侧物理坐标，若失败返回 0
 */
__declspec(dllexport) int find_icon_right_edge_native(int tray_left_phys, int rebar_right_phys) {
    HRESULT hr_co = CoInitializeEx(NULL, COINIT_MULTITHREADED);
    bool need_uninit = SUCCEEDED(hr_co);

    IUIAutomation* pAutomation = NULL;
    HRESULT hr = CoCreateInstance(
        CLSID_CUIAutomation,
        NULL,
        CLSCTX_INPROC_SERVER,
        IID_IUIAutomation,
        (void**)&pAutomation
    );

    if (FAILED(hr) || !pAutomation) {
        if (need_uninit) CoUninitialize();
        return 0;
    }

    // 1. 优先通过句柄极速获取任务栏 UIA 元素
    IUIAutomationElement* pTrayElem = NULL;
    HWND hwndTaskbar = FindWindowW(L"Shell_TrayWnd", NULL);
    if (hwndTaskbar) {
        pAutomation->ElementFromHandle((UIA_HWND)hwndTaskbar, &pTrayElem);
    }

    // 2. 若 FindWindowW 未取到，通过 RootElement 回退查找
    if (!pTrayElem) {
        IUIAutomationElement* pRoot = NULL;
        if (SUCCEEDED(pAutomation->GetRootElement(&pRoot)) && pRoot) {
            VARIANT varName;
            VariantInit(&varName);
            varName.vt = VT_BSTR;
            varName.bstrVal = SysAllocString(L"Shell_TrayWnd");

            IUIAutomationCondition* pCond = NULL;
            if (SUCCEEDED(pAutomation->CreatePropertyCondition(UIA_ClassNamePropertyId, varName, &pCond)) && pCond) {
                pRoot->FindFirst(TreeScope_Children, pCond, &pTrayElem);
                pCond->Release();
            }
            VariantClear(&varName);
            pRoot->Release();
        }
    }

    if (!pTrayElem) {
        pAutomation->Release();
        if (need_uninit) CoUninitialize();
        return 0;
    }

    RECT tbr = {0};
    pTrayElem->get_CurrentBoundingRectangle(&tbr);

    IUIAutomationCondition* pTrueCond = NULL;
    hr = pAutomation->CreateTrueCondition(&pTrueCond);
    if (FAILED(hr) || !pTrueCond) {
        pTrayElem->Release();
        pAutomation->Release();
        if (need_uninit) CoUninitialize();
        return 0;
    }

    IUIAutomationElementArray* pElemArray = NULL;
    hr = pTrayElem->FindAll(TreeScope_Descendants, pTrueCond, &pElemArray);
    pTrueCond->Release();

    double ir = 0.0;
    double tl = 0.0;
    double rr = 0.0;

    if (SUCCEEDED(hr) && pElemArray) {
        int count = 0;
        pElemArray->get_Length(&count);
        for (int i = 0; i < count; ++i) {
            IUIAutomationElement* pElem = NULL;
            if (SUCCEEDED(pElemArray->GetElement(i, &pElem)) && pElem) {
                BSTR bstrClass = NULL;
                pElem->get_CurrentClassName(&bstrClass);
                RECT r = {0};
                pElem->get_CurrentBoundingRectangle(&r);

                if (bstrClass) {
                    if (wcscmp(bstrClass, L"Taskbar.TaskListButtonAutomationPeer") == 0) {
                        if (r.left < r.right && r.top >= tbr.top - 2 && r.bottom <= tbr.bottom + 2) {
                            if ((double)r.right > ir) {
                                ir = (double)r.right;
                            }
                        }
                    } else if (wcscmp(bstrClass, L"TrayNotifyWnd") == 0) {
                        if (r.left < r.right) {
                            tl = (double)r.left;
                        }
                    } else if (wcscmp(bstrClass, L"ReBarWindow32") == 0) {
                        if (r.left < r.right) {
                            rr = (double)r.right;
                        }
                    }
                    SysFreeString(bstrClass);
                }
                pElem->Release();
            }
        }
        pElemArray->Release();
    }

    pTrayElem->Release();
    pAutomation->Release();
    if (need_uninit) CoUninitialize();

    if (ir <= 0.0) {
        return 0;
    }

    if (tl > 0.0 && rr > 0.0 && tray_left_phys > rebar_right_phys && (tl - rr) > 0.0) {
        double scale = (tl - rr) / (double)(tray_left_phys - rebar_right_phys);
        return (int)(rebar_right_phys + (ir - rr) / scale);
    }
    if (tl > 0.0 && tray_left_phys > 0) {
        return (int)(ir * (double)tray_left_phys / tl);
    }

    return 0;
}

} // extern "C"
