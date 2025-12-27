package com.sitech.controller.http;

import cn.hutool.core.collection.CollUtil;
import cn.hutool.core.util.StrUtil;
import cn.hutool.http.HttpRequest;
import cn.hutool.http.HttpResponse;
import cn.hutool.http.HttpUtil;
import com.alibaba.fastjson.JSONArray;
import com.alibaba.fastjson.JSONObject;
import com.google.gson.Gson;
import com.google.gson.JsonArray;
import com.google.gson.JsonParser;
import com.sitech.common.message.MessageCode;
import com.sitech.model.ai.AiScene;
import com.sitech.model.basedata.UserInfo;
import com.sitech.model.ltzb.SearchKlg;
import com.sitech.model.ltzb.YiXinSearchReq;
import com.sitech.model.ltzb.vo.SearchFaqVo;
import com.sitech.model.ltzb.vo.SearchVo;
import com.sitech.service.ai.Impl.AiSceneServiceImpl;
import com.sitech.service.aiklg.AiUserPermission;
import com.sitech.util.agent.PlatformMenu;
import com.sitech.util.exception.ResBean;
import com.sitech.util.session.Session;
import com.sitech.util.solr.SolrUtil;
import com.sitech.util.solr.TestSi_Tech001JsonData;
import com.sitech.util.tool.*;
import org.apache.commons.collections.CollectionUtils;
import org.apache.commons.lang3.StringUtils;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import javax.annotation.Resource;
import javax.servlet.http.HttpServletRequest;
import java.net.URLDecoder;
import java.text.SimpleDateFormat;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import java.util.stream.Stream;


@RestController
@EnableAutoConfiguration
@RequestMapping("/NewSearch")
public class SearchController {
    private static final Logger log = LoggerFactory.getLogger(SearchController.class);
    HashMap solrmp = Config.solrMp;
    HashMap kmsmp = Config.kmsMp;
    @Resource
    AiUserPermission aiUserPermission;
    @Resource
    AiSceneServiceImpl aiSceneService;

    /**
     * @category 知识搜索接口
     */
    @RequestMapping(value = "/NewSearchKlgInfo")
    public ResBean<PageBean> searchKlgInfo(@RequestBody SearchKlg klg, HttpServletRequest request) {
        ResBean<PageBean> resBean=new ResBean<>();
        String searchapiurl = Config.getKey(kmsmp, "searchapi.http.url");
        TestSi_Tech001JsonData jsondata = new TestSi_Tech001JsonData();
        String search_id = UUIDGenerator.getUUID();//搜索ID
        UserInfo userinfo = Session.getUserInfo(request);
        String lifestatus = klg.getLifeStatus() == null ? "" : klg.getLifeStatus();//预留查询条件
        String cityid = klg.getCityId() == null ? "" : klg.getCityId();//预留查询条件
        String source = "1";//1PC端2手机端3外部系统
        String keyword = "";//关键字
        if (klg.getKeyword() != null) {
            keyword = klg.getKeyword().trim().toLowerCase();
        }
        if (StrUtil.isNotBlank(keyword)) {
            // 英文双引号会引起搜索异常，替换为中文双引号
            String regex = "\"([^\"]*)\"";
            Pattern pattern = Pattern.compile(regex);
            Matcher matcher = pattern.matcher(keyword);
            while (matcher.find()) {
                String itemMatch = "“" + matcher.group(1) + "”";
                keyword = keyword.replace("\"" + matcher.group(1) + "\"", itemMatch);
            }
        }
        String solrType = klg.getSolrType();//排序方式
        String sortItems = klg.getSortItems();
        Boolean solrDesc = klg.getSolrDesc();//搜索排序true降序false升序
        String mm = Config.getCommonKey(solrmp, "mm");
        String bf = Config.getCommonKey(solrmp, "bf");

        String nokeyTimeOrder = Config.getKey(kmsmp, "zsmh_nokey_time_order");
        if (StringUtils.isNotEmpty(sortItems)) {
            jsondata.setSort(sortItems);
        } else if (StringUtils.isEmpty(solrType) && StrUtil.isBlank(keyword) && StrUtil.isNotBlank(nokeyTimeOrder) && "Y".equals(nokeyTimeOrder)) {
            jsondata.setSort("update_time," + ((solrDesc == null || solrDesc) ? "desc" : "asc"));
        } else if (StringUtils.isEmpty(solrType) || StringUtils.equals(solrType, "1")) {// 拼装搜索排序方式,默认文档得分倒序
            jsondata.setSort("score," + ((solrDesc == null || solrDesc) ? "desc" : "asc"));
        } else if (StringUtils.equals(solrType, "2")) { // 按更新时间排序
            jsondata.setSort("update_time," + ((solrDesc == null || solrDesc) ? "desc" : "asc"));
        } else if (StringUtils.equals(solrType, "3")) {// 按点击量排序
            jsondata.setSort("hitcount," + ((solrDesc == null || solrDesc) ? "desc" : "asc"));
        } else if (StringUtils.equals(solrType, "4")) {// 按标题排序
            jsondata.setSort("doctitle," + ((solrDesc == null || solrDesc) ? "desc" : "asc"));
        }  else if (StringUtils.equals(solrType, "8")) {// 按创建时间排序
            jsondata.setSort("crt_time," + ((solrDesc == null || solrDesc) ? "desc" : "asc"));
        } else if (StringUtils.equals(solrType, "9")) {// 按发布时间排序
            jsondata.setSort("start_time," + ((solrDesc == null || solrDesc) ? "desc" : "asc"));
        }

        //service_code 业务代码 知识搜索：A001
        String service_code = userinfo.getEp_id() + "A001";
        String fl = "solrid,docid,doctitle" + (klg.getFaqSearch() ?
                ",score,faq_da2,faq_da2_html,faq_wt2,faq_da2s,faq_wt2s,parentpath,cityname,mainquestionid,answerid" :
                ",doctitles,dockeyword,dockeywords,docabstracts,docabstract,html,htmls,attach,attachs,content,contents," +
                        "content2,content2s,ct_id,ct_name,parent_path_id,parent_path_name,hitcount,crt_time,update_time,update_user_id," +
                        "crt_user_name,update_user_name,crt_org_id,crt_org_name,tp_id,tp_name,city_id,city_name,city_ids,city_names,up_city_id,end_time,start_time,up_city_name," +
                        "lifestatus,is_top,is_recommend");
        //搜索入参拼装
        jsondata.setReq_id(search_id);
        jsondata.setReq_time(DateToolKit.getDateTime());
        jsondata.setStart(klg.getCurrentPage() * klg.getPageSize() - klg.getPageSize());
        jsondata.setRows(klg.getPageSize());
        jsondata.setOrg_code("1");
        jsondata.setService_code(service_code);
        jsondata.setInterface_code("si_tech001");
        jsondata.setUser_name("kms");
        jsondata.setPass_word("DF13D89A79DD133CD2E864F5276D8548");
        jsondata.setLoginid(userinfo.getId());
        jsondata.setLoginname(userinfo.getCloginname());
        jsondata.setKey_words(keyword);
        jsondata.setSource(source);
        // 2022.2.18修改为支持,分割的多个
        if (StringUtils.isNotBlank(klg.getLifeStatus()) && klg.getLifeStatus().indexOf(",") > -1) {
            jsondata.setLifestatus("");
        } else {
            jsondata.setLifestatus(lifestatus);
        }
        jsondata.setCityid(cityid);
        jsondata.setMm(mm);
        jsondata.setBf(bf);
        jsondata.setFl(fl);
        jsondata.setDf("doctitle");
        jsondata.setZj("solrid");

        //solr q 查询条件
        String queryStr = getSolrQuery(search_id, klg, userinfo, keyword);
        System.out.println("solr 查询条件: " + queryStr);
        jsondata.setQ(queryStr);

        //高亮字段
        if (!keyword.equals("")) {
            String highLight = klg.getFaqSearch() ? "faq_wt2s,faq_wt2" :
                    "doctitle,doctitles,dockeyword,dockeywords,docabstracts,docabstract,contents,content,content2s,content2";
            System.out.println("solr 高亮字段: " + highLight);
            jsondata.setLight(highLight);
        }
        String json = SolrUtil.getSi_Tech001Json(jsondata);

        System.out.println("入参json:" + json);
        log.info("入参json:" + json);
        try {
            //调用搜索引擎接口
            HashMap<String, Object> map = new HashMap<>();
            map.put("json", json);
            map.put("epId", userinfo.getEp_id());
            String netType = klg.getNetType();
            map.put("netType", netType);

            HashMap<String, String> headerMap = new HashMap();
            headerMap.put("headercheck", "U-B7EC4A21E66F4FEAAF5803E496049F54");
            log.info("search_api_url=" + searchapiurl);
            long t1 = System.currentTimeMillis();
            HttpRequest post = HttpUtil.createPost(searchapiurl);
            post.addHeaders(headerMap);

            HttpResponse response = HttpRequest.post(searchapiurl).form(map).addHeaders(headerMap).timeout(1000*60).execute();
            String result = response.body();
            long t2 = System.currentTimeMillis();
            log.info("搜索接口中search-api调用所花时间：" + (t2 - t1));
            if (result == null || result.equals("")) {
                resBean.setStatus(true);
                resBean.setErrMsg("暂无数据");
                return resBean;
            }

            //返回数据解析
            JSONObject obj = JSONObject.parseObject(result);
            JSONObject personObj = obj.getJSONObject("sitech");
            JSONObject head = personObj.getJSONObject("head");
            JSONObject body = personObj.getJSONObject("body");
            JSONArray message = new JSONArray();
            List<Object> resultList = new ArrayList();
            if (!(body == null)) {
                if (!"{}".equals(body.toString())) {
                    message = body.getJSONArray("message");
                }
                for (int i = 0; i < message.size(); i++) {//循环返回数据中的一条知识

                    JSONObject jsObject = message.getJSONObject(i);
                    try {
                        //---web传输汉字进行了编码，这里进行解码---
                        String solrid = URLDecoder.decode(jsObject.getString("solrid") == null ? "" : jsObject.getString("solrid"), "utf-8");
                        String docid = URLDecoder.decode(jsObject.getString("docid") == null ? "" : jsObject.getString("docid"), "utf-8");
                        String doctitle = URLDecoder.decode(jsObject.getString("doctitle") == null ? "" : jsObject.getString("doctitle"), "utf-8");
                        String dockeyword = URLDecoder.decode(jsObject.getString("dockeyword") == null ? "" : jsObject.getString("dockeyword"), "utf-8");
                        String docAbstract = URLDecoder.decode(jsObject.getString("docabstract") == null ? "" : jsObject.getString("docabstract"), "utf-8");
                        String html = URLDecoder.decode(jsObject.getString("html") == null ? "" : jsObject.getString("html"), "utf-8");
                        String ct_id2 = URLDecoder.decode(jsObject.getString("ct_id") == null ? "" : jsObject.getString("ct_id"), "utf-8");
                        String ct_name2 = URLDecoder.decode(jsObject.getString("ct_name") == null ? "" : jsObject.getString("ct_name"), "utf-8");
                        String hitcount = URLDecoder.decode(jsObject.getString("hitcount") == null ? "" : jsObject.getString("hitcount"), "utf-8");
                        String parent_path_id = URLDecoder.decode(jsObject.getString("parent_path_id") == null ? "" : jsObject.getString("parent_path_id"), "utf-8");
                        String parent_path_name = URLDecoder.decode(jsObject.getString("parent_path_name") == null ? "" : jsObject.getString("parent_path_name"), "utf-8");
                        String parentpath = URLDecoder.decode(jsObject.getString("parentpath") == null ? "" : jsObject.getString("parentpath"), "utf-8");
                        String update_time = URLDecoder.decode(jsObject.getString("update_time") == null ? "" : jsObject.getString("update_time"), "utf-8");
                        String update_user_id = URLDecoder.decode(jsObject.getString("update_user_id") == null ? "" : jsObject.getString("update_user_id"), "utf-8");
                        String update_user_name = URLDecoder.decode(jsObject.getString("update_user_name") == null ? "" : jsObject.getString("update_user_name"), "utf-8");
                        String content = URLDecoder.decode(jsObject.getString("content") == null ? "" : jsObject.getString("content"), "utf-8");
                        String contents = URLDecoder.decode(jsObject.getString("contents") == null ? "" : jsObject.getString("contents"), "utf-8");
                        String crt_time = URLDecoder.decode(jsObject.getString("crt_time") == null ? "" : jsObject.getString("crt_time"), "utf-8");
                        String end_time = URLDecoder.decode(jsObject.getString("end_time") == null ? "" : jsObject.getString("end_time"), "utf-8");
                        String start_time = URLDecoder.decode(jsObject.getString("start_time") == null ? "" : jsObject.getString("start_time"), "utf-8");

                        String crt_user_name = URLDecoder.decode(jsObject.getString("crt_user_name") == null ? "" : jsObject.getString("crt_user_name"), "utf-8");
                        String crt_org_name = URLDecoder.decode(jsObject.getString("crt_org_name") == null ? "" : jsObject.getString("crt_org_name"), "utf-8");

                        String tpId = URLDecoder.decode(jsObject.getString("tp_id") == null ? "" : jsObject.getString("tp_id"), "utf-8");
                        String tpName = URLDecoder.decode(jsObject.getString("tp_name") == null ? "" : jsObject.getString("tp_name"), "utf-8");
                        String attach = URLDecoder.decode(jsObject.getString("attach") == null ? "" : jsObject.getString("attach"), "utf-8");

                        String city_id = URLDecoder.decode(jsObject.getString("city_ids") == null ? "" : jsObject.getString("city_ids"), "utf-8");
                        String city_name = URLDecoder.decode(jsObject.getString("city_names") == null ? "" : jsObject.getString("city_names"), "utf-8");
                        String up_city_id = URLDecoder.decode(jsObject.getString("up_city_id") == null ? "" : jsObject.getString("up_city_id"), "utf-8");
                        String up_city_name = URLDecoder.decode(jsObject.getString("up_city_name") == null ? "" : jsObject.getString("up_city_name"), "utf-8");

                        //faq 返回数据
                        String faq_wt = URLDecoder.decode(jsObject.getString("faq_wt2") == null ? "" : jsObject.getString("faq_wt2"), "utf-8");
                        String faq_da = URLDecoder.decode(jsObject.getString("faq_da2") == null ? "" : jsObject.getString("faq_da2"), "utf-8");
                        String cityName = URLDecoder.decode(jsObject.getString("cityname") == null ? "" : jsObject.getString("cityname"), "utf-8");

                        //新加lifestatus，is_top,is_recommend
                        String lifeStatus = URLDecoder.decode(jsObject.getString("lifestatus") == null ? "" : jsObject.getString("lifestatus"), "utf-8");
                        String is_top = URLDecoder.decode(jsObject.getString("is_top") == null ? "" : jsObject.getString("is_top"), "utf-8");
                        String is_recommend = URLDecoder.decode(jsObject.getString("is_recommend") == null ? "" : jsObject.getString("is_recommend"), "utf-8");
                        if (keyword.equals("")) {
                            content = Common.SubStr(content.trim(), 150);
                        }
                        //未搜索content字段只搜索了contents字段的，取contents的值。 解决bss销售品只搜索contents字段未高亮问题
                        if (!queryStr.contains("content:") && queryStr.contains("contents:")) {
                            content = contents;
                        }
                        //若配置了条目摘要字段，则内容=配置的字段的值
                        String search_show_item;
                        try {
                            search_show_item = Config.getKey(Config.kmsMp, "search_show_item");
                        } catch (Exception e) {
                            search_show_item = "";
                        }
                        if (StringUtils.isNotEmpty(search_show_item) && search_show_item.equals("content2")) {
                            String content2 = URLDecoder.decode(jsObject.getString("content2") == null ? "" : jsObject.getString("content2"), "utf-8");
                            if (StringUtils.isNotEmpty(content2)) {
                                if (content2.length() > 250) {
                                    content2 = Common.SubStr(content2.trim(), 250);
                                }
                                content = content2;
                            }
                        }
                        content = filterFileIdStr(content);
                        if (klg.getFaqSearch()) {
                            SearchFaqVo searchFaqVo = new SearchFaqVo();
                            searchFaqVo.setSolrId(solrid);
                            searchFaqVo.setDocId(docid);
                            searchFaqVo.setDocTitle(doctitle);
                            searchFaqVo.setFaq_wt2(faq_wt);
                            searchFaqVo.setFaq_da2(faq_da);
                            searchFaqVo.setCityName(cityName);
                            searchFaqVo.setParentPath(parentpath);
                            resultList.add(searchFaqVo);
                        } else {
                            SearchVo searchVo = new SearchVo();
                            searchVo.setSolrid(solrid);
//                            searchVo.setStart_time(start_time);
//                            searchVo.setEnd_time(end_time);
                            searchVo.setDocid(docid);
                            searchVo.setCrt_org_name(crt_org_name);
                            searchVo.setCrt_user_name(crt_user_name);

                            //湖北政企需求：知识标题后边增加预警信息(1个月到期-红色字体，3个月到期-橙色字体）
                            String dateTitle = getDateTitle(doctitle, end_time);
                            searchVo.setDoctitle(dateTitle);
                            searchVo.setDockeyword(dockeyword.replace("[", "").replace("]", ""));
                            searchVo.setDocAbstract(docAbstract);
                            searchVo.setHtml(html);
                            searchVo.setContent(content.replace("null", "").replace("[", "").replace("]", "").replace("fontcolor", "font color"));
                            if (StringUtils.isNotBlank(searchVo.getContent())) {
                                if (StringUtils.length(content) > 250) {
                                    int keyWordLength = ("<font color=\"red\">" + keyword + "</font>").length();
                                    int indexStr = searchVo.getContent().indexOf("<font color=\"red\">" + keyword + "</font>");
                                    if (indexStr > (250 - keyWordLength) && 250 > indexStr) {
                                        searchVo.setContent(searchVo.getContent().substring(0, indexStr + keyWordLength));
                                    } else {
                                        searchVo.setContent(searchVo.getContent().substring(0, 250));
                                    }
                                }
                            }
                            searchVo.setCt_id(ct_id2);
                            searchVo.setCt_name(ct_name2);
                            searchVo.setHitcount(hitcount);
                            searchVo.setParent_path_id(parent_path_id);
                            searchVo.setParent_path_name(parent_path_name.contains("_") ? parent_path_name.substring(0, parent_path_name.indexOf("_")) : parent_path_name);
                            searchVo.setUpdate_time(update_time);
                            searchVo.setUpdate_user_id(update_user_id);
                            searchVo.setUpdate_user_name(update_user_name);
                            searchVo.setCrt_time(crt_time);
                            searchVo.setTpId(tpId);
                            searchVo.setTpName(tpName);
                            searchVo.setCity_id(city_id);
                            searchVo.setCity_name(city_name);
                            searchVo.setUp_city_id(up_city_id);
                            searchVo.setUp_city_name(up_city_name);
                            searchVo.setLifestatus(lifeStatus);
                            searchVo.setIs_top(is_top);
                            searchVo.setIs_recommend(is_recommend);
                            searchVo.setAttach(attach);
                            resultList.add(searchVo);
                        }
                    } catch (Exception e) {
                        e.printStackTrace();
                        log.error("系统异常：", e);
                    }
                }
            } //返回数据中的一条知识循环结束
            int count = Integer.parseInt(head.get("count").toString());
            int pageCount = count % klg.getPageSize() == 0 ? (count / klg.getPageSize()) : (count / klg.getPageSize()) + 1;

            long t3 = System.currentTimeMillis();
            log.info("搜索结果解析所用时间：" + (t3 - t2));

            PageBean<Object> pageBean = new PageBean<>();
            pageBean.setCurrentPage(klg.getCurrentPage());
            pageBean.setPageSize(klg.getPageSize());
            pageBean.setTotalNum(count);
            pageBean.setTotalPage(pageCount);
            pageBean.setSearch_id(search_id);
            pageBean.setL(resultList);
            String is_search_categoryklgcount = Config.getKey(kmsmp, "is_search_categoryklgcount");
            if (StringUtils.isNotBlank(is_search_categoryklgcount) && "Y".equals(is_search_categoryklgcount)) {
                SearchKlg k = klg;
                k.setCtId(null);
                TestSi_Tech001JsonData data = jsondata;
                data.setFl("parent_path_id");
                String q = this.getSolrQuery(search_id, k, userinfo, keyword);
                log.info("============【统计】查询条件：{}", q);
                data.setQ(q);
                data.setRows(99999);
                data.setReq_id(UUIDGenerator.getUUID());
                String js = SolrUtil.getSi_Tech001Json(data);
                log.info("============【统计】查询json：{}", js);
                map.put("json", js);
                // 赵总要求,如果无关键词则不统计
                log.info("=============开始统计============");
                if (StrUtil.isBlank(klg.getKeyword())) {
                    log.info("=============关键词为空============");
                    pageBean.setTpCount(CollUtil.newArrayList(new HashMap<>()));
                } else {
                    pageBean.setTpCount(getCountByCt2(data));
                }
            }
            resBean.setStatus(true);
            resBean.setErrMsg("请求成功");
            resBean.setData(pageBean);
            return resBean;
        } catch (Exception e) {
            log.error("搜索异常:", e);
            e.printStackTrace();
            resBean.setStatus(false);
            resBean.setErrMsg("Failed to fetch");
            return resBean;
        }
    }

    /**
     * @category 易信门户帖子搜索
     */
    @RequestMapping(value = "/searchFromYiXinPortal")
    public ResBean searchFromYiXinPortal(@RequestBody YiXinSearchReq yiXinSearchReq) {
        log.info("【易信门户帖子搜索】入参 = {}", yiXinSearchReq);
        if (Session.getUserInfo() == null) {
            return new ResBean<>(false, MessageCode.ERROR,"无用户登录信息");
        }
        UserInfo user = Session.getUserInfo();
        yiXinSearchReq.setOnconuuid(user.getId());
        yiXinSearchReq.setOrgNo(user.getOrgid());
//        yiXinSearchReq.setOnconuuid("oncon100000013301");
//        yiXinSearchReq.setOrgNo("10000");
        try{
            return aiUserPermission.searchFromYiXinPortal(yiXinSearchReq);
        }catch (Exception e){
            log.error("【易信门户帖子搜索】error = {}", e.toString());
            return new ResBean(false, MessageCode.ERROR,"搜索失败");
        }
    }

    /**
     * solr q: 查询条件
     */
    private String getSolrQuery(String search_id, SearchKlg klg, UserInfo userinfo, String keyword) {
        StringBuilder q;//查询条件

        boolean bssSelected = klg.getIsBssSelected();//是否勾选bss销售品

        String cityid = klg.getCityId() == null ? "" : klg.getCityId();
        String ct_id = klg.getCtId();//分类ID
        String defaultEpId = Config.getCommonKey(Config.kmsMp, "defaulEpId");
        if (StrUtil.equals("jskf", defaultEpId) && StringUtils.isNotBlank(ct_id)) {
            ct_id = "_" + ct_id + "_";
        }
        String startTime = klg.getStartTime();//门户搜搜发布时间范围-开始
        String endTime = klg.getEndTime();//门户搜搜发布时间范围-结束
        String klgIds = klg.getKlgIds();//知识id不为空根据知识id搜
        String isTop = klg.getIsTop();//根据是否指定查询

        String isOpenAreaCon = Config.getKey(kmsmp, "is_open_area_control");
        if (StrUtil.isNotEmpty(isOpenAreaCon) && "Y".equals(isOpenAreaCon)) {
            klg.setC_id(userinfo.getCity_id());
            klg.setAreaCode(userinfo.getCity_id());
        }

        if (StringUtils.isNotEmpty(klgIds)) {
            q = new StringBuilder("(");
            String[] klgIdArr = klgIds.split(",");
            for (String klgId :
                    klgIdArr) {
                q.append("docid:").append(klgId).append(" OR ");
            }
            q = new StringBuilder(q.substring(0, q.lastIndexOf("OR") - 1)).append(")");
        } else if (StringUtils.isNotEmpty(keyword)) {
            q = getQByKeyWord(search_id, keyword, bssSelected, cityid, userinfo, klg);
        } else {
            q = new StringBuilder("(docstatus:3 OR docstatus:5 OR docstatus:6)");
        }
        // 知识搜索：若传递了lifestatus搜索条件，则按照lifestatus传值进下查询。若没有传值，则仅查询lifestatus=1的值;
        // 2022.2.18修改为支持,分割的多个
        if (StringUtils.isNotBlank(klg.getLifeStatus()) && klg.getLifeStatus().indexOf(",") > -1) {
            String[] lss = klg.getLifeStatus().split(",");
            for (int i = 0; i < lss.length; i++) {
                q.append((i == 0 ? " AND (" : "") + "lifestatus:" + lss[i] + ((lss.length > (i + 1)) ? " OR " : ")"));
            }
        } else {
            q.append(" AND lifestatus:").append(StringUtils.isEmpty(klg.getLifeStatus()) ? "1" : klg.getLifeStatus());
        }

        //创建时间查询
        String isDate = Config.getKey(kmsmp, "klg_is_date");
        if (StringUtils.isNotEmpty(isDate) && "Y".equals(isDate)
                && (StringUtils.isNotEmpty(startTime) || StringUtils.isNotEmpty(endTime))) {
            startTime = StrUtil.isNotBlank(startTime) ? startTime : "*";
            endTime = StrUtil.isNotBlank(endTime) ? (endTime + " 23:59:59") : "*";
            q.append(" AND (crt_time:[\\\"").append(startTime).append("\\\" TO \\\"").append(endTime).append("\\\"]) ");
        }
        //发布时间查询
        String isStartTime = Config.getKey(kmsmp, "klg_is_start_time");
        if (StringUtils.isNotEmpty(isStartTime) && "Y".equals(isStartTime)
                && (StringUtils.isNotEmpty(startTime) || StringUtils.isNotEmpty(endTime))) {
            startTime = StrUtil.isNotBlank(startTime) ? startTime : "*";
            endTime = StrUtil.isNotBlank(endTime) ? (endTime.contains(" 00:00:00") ?
                    endTime.replace(" 00:00:00", " 23:59:59") : endTime) : "*";

            //endTime为 * 时，加双引号有bug，需要去掉双引号
            q.append(" AND (start_time:[\\\"").append(startTime).append("\\\" TO ").
                    append("*".equals(endTime) ? "" : "\\\"").append(endTime).append("*".equals(endTime) ? "" : "\\\"").
                    append("]) ");
        }

        // 权限控制  查询用户的知识库和文件夹权限
        Map<String, Object> userMap=new HashMap<>();
        userMap.put("epId",klg.getEp_id());
        userMap.put("userId",userinfo.getId());
        userMap.put("ctIds",klg.getCt_id());
        userMap.put("folderLabelCode",klg.getFolderLabelCode());
        String userCtIds=null;

        String ctidFilterPermission = Config.getCommonKey(Config.kmsMp, "ctid_filter_permission");
        log.info("关联知识库搜索权限限制Y={}",ctidFilterPermission);

        if(StrUtil.isNotEmpty(klg.getScene_id())){
            AiScene aiSceneItem = new AiScene();
            aiSceneItem.setId(klg.getScene_id());
            aiSceneItem.setFormal(PlatformMenu.getTableFlag(klg.getChat_source_href()));
            ct_id = aiSceneService.queryKlgIdFromAiSceneKlg(aiSceneItem);
            userMap.put("ctIds",ct_id);
        }
        if (StrUtil.isEmpty(ct_id)){
            Map<String,String> userPermissionMap=aiUserPermission.getUserPermission(userMap);
            // 3 根据用户ID查询用户所有的level级部门ID的权限ctIds和parentPathId

            if(null!=userPermissionMap&&userPermissionMap.containsKey("ctIds")) {
                userCtIds = userPermissionMap.get("ctIds");
                log.info("全文检索用户最终拥有知识库权限的的userCtIds={}",userCtIds);
            }
        }else{
            userCtIds = userMap.get("ctIds").toString();
            log.info("未开启权限直接使用助手知识库ID={}",userCtIds);
        }


        if(StrUtil.isNotEmpty(userCtIds)){
            List<String> ctIdsList = Stream.of(userCtIds.split(","))
                    .map(String::trim) // 去除每个元素的首尾空格
                    .collect(Collectors.toList());
            for (int i = 0; i < ctIdsList.size(); i++) {
                if (i == 0) {
                    q.append(" AND (ct_id:").append(ctIdsList.get(i));
                } else {
                    q.append(" OR ct_id:").append(ctIdsList.get(i));
                }
                if (i == ctIdsList.size() - 1) {
                    q.append(")");
                }
            }
        }else if(StrUtil.isEmpty(klg.getDataset_belong())){
            q.append(" AND (ct_id:0000)");
        }
        if (StrUtil.isNotEmpty(klg.getDataset_belong())){
            q.append(" AND (item_id:").append(klg.getDataset_belong());
            if("0".equals(klg.getDataset_belong())){
                q.append(" AND crt_user_id:").append(userinfo.getId());
            }
            q.append(") ");
        }
//        // 搜索分类是否只搜索选中的分类is_search_selectcategory_klg----Y是N或不配置否
//        if (StrUtil.isNotBlank(ct_id) && StrUtil.equals("Y", Config.getKey(kmsmp, "is_search_selectcategory_klg"))) {
//            if (StrUtil.isBlank(klg.getKeyword())) {
//                q.append(" AND ct_id:" + ct_id);
//            } else {
//                q.append(" AND parent_path_id:*").append(ct_id).append("*");
//            }
//        }

        try {
            String searchRoleCt = Config.getKey(Config.kmsMp, "search_role_ct");
            if (StringUtils.isNotEmpty(searchRoleCt)) {
                AtomicReference<String> roleCtQ = new AtomicReference<>("");
                JsonArray jsonArray = new JsonParser().parse(searchRoleCt).getAsJsonArray();
                jsonArray.forEach(obj -> {
                    JsonArray roleIds = obj.getAsJsonObject().get("roleIds").getAsJsonArray();
                    ArrayList roleIdList = new Gson().fromJson(roleIds, ArrayList.class);
                    if (!CollectionUtils.containsAny(roleIdList, Arrays.asList(userinfo.getCroleid().split(",")))) {
                        JsonArray ctIds = obj.getAsJsonObject().get("ctIds").getAsJsonArray();
                        ctIds.forEach(ctId -> {
                            roleCtQ.set(roleCtQ.get() + " AND (-parent_path_id:*" + ctId.getAsString() + "*) ");
                        });
                    }
                });
                q.append(roleCtQ.get());
            }
        } catch (Exception e) {
            log.error("获取配置搜索角色分类权限关系异常：", e);
        }

        if (StringUtils.isNotEmpty(isTop)) {
            q.append(" AND (is_top:").append(isTop).append(")");
        }

        // 部门id
        String org_id = userinfo.getOrgid();
        if(StringUtils.isNotEmpty(org_id)){
            q.append(" AND crt_org_id:" + org_id);
        }

        return q.toString();
    }

    private StringBuilder getQByKeyWord(String search_id, String keyword, boolean bssSelected, String cityId, UserInfo userinfo, SearchKlg klg) {
        //权重
        String docTitlesBoost = Config.getCommonKey(solrmp, "doctitles_boost");//知识标题全词
        String docKeywordsBoost = Config.getCommonKey(solrmp, "dockeywords_boost");//知识关键词全词
        String contents_boost = Config.getCommonKey(solrmp, "contents_boost");//内容全词
        String docTitleBoost = Config.getCommonKey(solrmp, "doctitle_boost");//知识标题拆词
        String docKeywordBoost = Config.getCommonKey(solrmp, "dockeyword_boost");//知识关键词拆词
        String docabstractsBoost = Config.getCommonKey(solrmp, "docabstracts_boost");//知识关键(标签)词全词
        String docabstractBoost = Config.getCommonKey(solrmp, "docabstract_boost");//知识关键词(标签)


        //老版各字段权重说明
        docTitlesBoost = StringUtils.isEmpty(docTitlesBoost) ? "2500" : docTitlesBoost;
        docKeywordsBoost = StringUtils.isEmpty(docKeywordsBoost) ? "500" : docKeywordsBoost;//关键字，被标签占用
        docabstractsBoost = StringUtils.isEmpty(docabstractsBoost) ? "300" : docabstractsBoost;//关键字
        docTitleBoost = StringUtils.isEmpty(docTitleBoost) ? "100" : docTitleBoost;
        docKeywordBoost = StringUtils.isEmpty(docKeywordBoost) ? "70" : docKeywordBoost;//关键字，被标签占用
        docabstractBoost = StringUtils.isEmpty(docabstractBoost) ? "50" : docabstractBoost;//关键字
        contents_boost = StringUtils.isEmpty(contents_boost) ? "200" : contents_boost;

        String search_show_item;
        try {
            search_show_item = Config.getKey(Config.kmsMp, "search_show_item");
        } catch (Exception e) {
            search_show_item = "";
        }

        boolean isSearchContent;
        boolean isSearchAttach;
        try {
            isSearchContent = klg.getSearchContent();
            isSearchAttach = klg.getSearchAttach();
        } catch (Exception e) {
            isSearchContent = true;
            isSearchAttach = false;
        }
        keyword = keyword.replace(":", "：");// 英文:会引起搜索异常，替换为中文：
        keyword = keyword.replaceAll("\\\\n", "\n");
        String rawWord = keyword;
        //转义搜索词中的 + - / [ ] ( )
        keyword = escapeSpecialChar(keyword);
        StringBuilder q;
        if (bssSelected) {
            //如果勾选了BSS销售品只根据知识内容全词匹配搜索
            q = new StringBuilder("contents:\\\"" + keyword + "\\\" ");
        } else {
            if (keyword.contains(" ")) {
                keyword = keyword.replaceAll("\\s+", " ");// 若包含2个空格，则替换为一个空格
                String[] kwArr = keyword.split(" ");
                q = new StringBuilder();
                for (String s : kwArr) {
                    q.append("(doctitles:\\\"").append(s).append("\\\"^").append(docTitlesBoost).
                            append(" OR ").append("dockeywords:\\\"").append(s).append("\\\"^").append(docKeywordsBoost).
                            append(" OR ").append("docabstracts:\\\"").append(s).append("\\\"^").append(docabstractsBoost).
                            append(" OR ").append("doctitle:").append(s).append("^").append(docTitleBoost).
                            append(" OR ").append("dockeyword:").append(s).append("^").append(docKeywordBoost).
                            append(" OR ").append("docabstract:").append(s).append("^").append(docabstractBoost).
                            append(isSearchContent ? " OR contents:\\\"" + s + "\\\"^" + contents_boost + " OR " + "content:" + s : "").
                            append(isSearchAttach ? " OR attachs:\\\"" + s + "\\\"" + " OR " + "attach:" + s : "").
                            append(StringUtils.isNotEmpty(search_show_item) ? "" : " OR content2s:\\\"" + s + "\\\"^" + contents_boost + " OR " + "content2:" + s).
                            append(") AND ");
                }
                if (q.length() > 0) {
                    q = new StringBuilder(q.substring(0, q.lastIndexOf("AND")));
                }
            } else {
                q = new StringBuilder("(doctitles_all:\\\"" + keyword + "\\\"^99999999 OR " +
                        "doctitles:\\\"" + keyword + "\\\"^" + docTitlesBoost + " OR " +
                        "dockeywords:\\\"" + keyword + "\\\"^" + docKeywordsBoost + " OR " +
                        "docabstracts:\\\"" + keyword + "\\\"^" + docabstractsBoost + " OR " +
                        "doctitle:" + keyword + "^" + docTitleBoost + "  OR " +
                        "dockeyword:" + keyword + "^" + docKeywordBoost + "  OR " +
                        "docabstract:" + keyword + "^" + docabstractBoost +
                        getBusQuery(rawWord) + getC(search_id, cityId, keyword, userinfo));
                if (isSearchContent) {
                    q.append(" OR contents:\\\"").append(keyword).append("\\\"^").append(contents_boost).
                            append(" OR ").append("content:").append(keyword);
                }
                if (isSearchAttach) {
                    q.append(" OR attachs:\\\"").append(keyword).append("\\\"").append(" OR ").
                            append("attach:").append(keyword);
                }
                if (StringUtils.isNotEmpty(search_show_item)) {
                    q.append(" OR content2s:\\\"").append(keyword).append("\\\"^").append(contents_boost).
                            append(" OR ").append("content2:").append(keyword);
                }
                q.append(")");
            }
        }
        q.append(" AND (docstatus:3 OR docstatus:5 OR docstatus:6)");//知识状态 3:正常
        return q;
    }

    /**
     * 过滤词
     */
    private StringBuilder getQByFilterKey(String filterKey) {
        StringBuilder fq = new StringBuilder();
        fq.append(" AND (-doctitles_all:\\\"" + filterKey + "\\\" AND " +
                "-doctitles:\\\"" + filterKey + "\\\" AND " +
                "-dockeywords:\\\"" + filterKey + "\\\" AND " +
                "-docabstracts:\\\"" + filterKey + "\\\" AND " +
                "-doctitle:\\\"" + filterKey + "\\\" AND " +
                "-dockeyword:\\\"" + filterKey + "\\\" AND " +
                "-docabstract:\\\"" + filterKey + "\\\" AND " +
                "-contents:\\\"" + filterKey + "\\\" AND " +
                "-content:\\\"" + filterKey + "\\\" ) ");
        return fq;
    }

    private String getBusQuery(String keyword) {
        try {
            Set<String> businessWordSet = getBusinessWordSet();
            StringBuilder targetBusWord = new StringBuilder();
            for (String busWord :
                    businessWordSet) {
                if (StringUtils.isNotEmpty(keyword) && keyword.trim().toLowerCase().contains(busWord.trim().toLowerCase())) {
                    keyword = keyword.replace(busWord.trim().toLowerCase(), "");
                    targetBusWord.append(busWord.trim().toLowerCase());
                }
            }
            if (StringUtils.isNotEmpty(targetBusWord.toString())) {
                log.info("命中业务词:" + targetBusWord);
            }
            String docTitlesBusBoost = Config.getCommonKey(solrmp, "doctitles_bus_boost");//知识标题业务词全词
            String docKeywordsBusBoost = Config.getCommonKey(solrmp, "dockeywords_bus_boost");//知识关键词业务词全词
            String docTitleBusBoost = Config.getCommonKey(solrmp, "doctitle_bus_boost");//知识标题业务词拆词
            String docKeywordBusBoost = Config.getCommonKey(solrmp, "dockeyword_bus_boost");//知识关键词业务词拆词
            if (!targetBusWord.toString().equals("") && !keyword.equals("")) {
                String busWord = escapeSpecialChar(targetBusWord.toString());
                keyword = escapeSpecialChar(keyword);
                String a1 = "\\\"" + busWord + "\\\"^" + docTitlesBusBoost;
                String a2 = "\\\"" + busWord + "\\\"^" + docKeywordsBusBoost;
                String a3 = busWord + "^" + docTitleBusBoost;
                String a4 = busWord + "^" + docKeywordBusBoost;
                return " OR doctitles:" + a1 + keyword + " OR docabstracts:" + a2
                        + keyword + " OR doctitle:" + a3 + keyword
                        + "  OR docabstract:" + a4 + keyword;
            }
        } catch (Exception e) {
            log.error("getBusQuery拼接业务词异常：", e);
        }
        return "";
    }

    public static String getC(String search_id, String cityId, String keyword, UserInfo userinfo) {
        StringBuilder solrids = new StringBuilder();
        try {
            String epId = userinfo.getEp_id();

            String qc = "";
            if (cityId != null && !cityId.equals("")) {
                qc = "(evl_word_all:\\\"" + keyword + "\\\"^60000  OR evl_words:\\\"" + keyword
                        + "\\\") AND cityid:*" + cityId + "*";
            } else {
                qc = "(evl_word_all:\\\"" + keyword + "\\\"^60000  OR evl_words:\\\"" + keyword
                        + "\\\")";
            }


            String sortType = "evl_count,desc";
            String service_code = "A008";
            String fl = "solrid,docid,doctitle,evl_word,evl_word_all,evl_count,cityid,cityname";
            String light = "";

            TestSi_Tech001JsonData jsondata = new TestSi_Tech001JsonData();
            //搜索入参拼装
            jsondata.setReq_id(search_id);
            jsondata.setReq_time(DateToolKit.getDateTime());
            jsondata.setStart(0);
            jsondata.setRows(10);
            jsondata.setOrg_code("1");
            jsondata.setService_code(epId + service_code);
            jsondata.setInterface_code("si_tech001");
            jsondata.setUser_name("kms");
            jsondata.setPass_word("DF13D89A79DD133CD2E864F5276D8548");
            jsondata.setSort(sortType);
            jsondata.setLoginid(userinfo.getId());
            jsondata.setLoginname(userinfo.getCloginname());
            jsondata.setKey_words(keyword);
            jsondata.setFl(fl);
            jsondata.setDf("doctitle");
            jsondata.setZj("solrid");

            jsondata.setQ(qc);

            jsondata.setLight(light);

            String json = SolrUtil.getSi_Tech001Json(jsondata);

            System.out.println("入参json:" + json);
            log.info("入参json:" + json);
            try {
                String searchApiUrl = Config.getCommonKey(Config.solrMp, "searchapi.http.url");
                //调用搜索引擎接口
                HashMap<String, String> map = new HashMap<>();
                map.put("json", json);
                map.put("epId", epId);
                log.info("search_api_url=" + searchApiUrl);
                String result = HttpClientUtil.doPost(searchApiUrl, map);

                if (result != null && !"".equals(result)) {
                    System.out.println("搜索结果:" + result);
                    JSONObject obj = JSONObject.parseObject(result);
                    JSONObject personObj = obj.getJSONObject("sitech");
                    JSONObject body = personObj.getJSONObject("body");
                    JSONArray message = new JSONArray();
                    if (!"{}".equals(body.toString())) {
                        message = body.getJSONArray("message");
                        for (int i = 0; i < message.size(); i++) {
                            JSONObject jsObject = message.getJSONObject(i);
                            String solrid = URLDecoder.decode(jsObject
                                    .getString("solrid"), "utf-8");
                            String evl_count = URLDecoder.decode(jsObject
                                    .getString("evl_count"), "utf-8");
                            if (StringUtils.isEmpty(evl_count)) {
                                continue;
                            }
                            int evl_counts = Integer.parseInt(evl_count);
                            int boost = 1;
                            if (evl_counts < 10) {
                                boost = 500000;
                            }
                            if (evl_counts >= 10 && evl_counts < 100) {
                                boost = 50000;
                            }
                            if (evl_counts >= 100 && evl_counts < 1000) {
                                boost = 5000;
                            }
                            if (evl_counts >= 1000 && evl_counts < 10000) {
                                boost = 500;
                            }
                            if (evl_counts >= 10000) {
                                boost = 50;
                            }
                            long evl = evl_counts * boost;
                            solrids.append(" solrid:").append(solrid).append("^").append(evl).append(" OR ");
                            if (i == 1) {
                                break;
                            }
                        }
                    }
                    if (!solrids.toString().equals("")) {
                        solrids = new StringBuilder(" OR "
                                + solrids.substring(0, solrids.length() - 4));
                        System.out.println("关键词" + keyword + "命中缓存,solrIds=" + solrids);
                    }
                }
            } catch (Exception e) {
                log.error("系统异常：", e);
            }
        } catch (Exception e) {
            log.error("获取缓存异常：", e);
        }
        return solrids.toString();

    }

    /**
     * 转义搜索词中的 + - / [ ] ( )
     */
    private String escapeSpecialChar(String word) {
        word = word.replace("-", "\\\\-").replace("+", "\\\\+").
                replace("/", "\\\\/").replace("[", "\\\\[").replace("]", "\\\\]").
                replace("(", "\\\\(").replace(")", "\\\\)");
        return word;
    }

    public Set<String> getBusinessWordSet() {
        try {
            String business_words = Config.getCommonKey(Config.solrMp, "business_words");
            return Arrays.stream(business_words.split(",")).collect(Collectors.toSet());
        } catch (Exception e) {
            log.error("读取业务词配置失败，", e);
            return null;
        }
    }

    /**
     * 过滤content中的附件id
     */
    private String filterFileIdStr(String content) {
        try {
            String regex = "[A-Za-z0-9]{32}_+";
            return content.replaceAll(regex, "");
        } catch (Exception e) {
            log.error("过滤附件id异常", e);
            return content;
        }
    }

    /**
     * 获取分组搜索结果数
     */
    private List getCountByTp(String q, String req_id, String epId) {
        System.out.println(q);
        List resultList = new ArrayList();

        try {
            //查询分组(solr)
            TestSi_Tech001JsonData jsonData = new TestSi_Tech001JsonData();
            jsonData.setReq_id(req_id);
            jsonData.setService_code(epId + "A001");
            jsonData.setInterface_code("si_tech002");
            jsonData.setQ(q);
            jsonData.setStart(0);
            jsonData.setRows(1);
            //目前安徽需求根据一级知识分类分组查询
            if (StrUtil.equals(Config.getKey(kmsmp,"is_shanghai"),"Y")){
                //上海按照知识类型分组
                jsonData.setFacet_field("type");
            }else {
                jsonData.setFacet_field("parent_path_id");

            }

            //调用搜索引擎接口,方法内部读取配置中心searchapi.http.url
            String result = SolrUtil.SolrPost(jsonData);

            //返回数据解析
            JSONObject obj = JSONObject.parseObject(result);
            JSONObject personObj = obj.getJSONObject("sitech");
            JSONObject body = personObj.getJSONObject("body");
            JSONArray message = new JSONArray();

            if (!(body == null)) {
                if (!"{}".equals(body.toString())) {
                    message = body.getJSONArray("message");
                }
                if (StrUtil.equals(Config.getKey(kmsmp,"is_shanghai"),"Y")){
                    resultList.addAll(message);
                    return resultList;
                }
                //默认一级目录id为***_****_****第二个id 过滤->处理->分组聚合->遍历赋值
                Object resuObj = message.stream().filter(item -> {
                    String parent_path_id = (String) ((JSONObject) item).keySet().toArray()[0];
                    return StringUtils.isNotEmpty(parent_path_id) && parent_path_id.contains("_");
                }).map(item -> {
                    String parent_path_id = (String) ((JSONObject) item).keySet().toArray()[0];
                    String count = (String) ((JSONObject) item).values().toArray()[0];
                    //一级知识分类
                    String ct_id = parent_path_id.split("_")[1];
                    Map<String, Object> map = new HashMap<>();
                    map.put("ct_id", ct_id);
                    map.put("count", Long.parseLong(count));
                    return map;
                }).collect(Collectors.groupingBy(map ->
                        ((Map) map).get("ct_id"), Collectors.summarizingLong(map -> ((Long) ((Map) map).get("count")))));
                ((Map) resuObj).forEach(
                        (k, v) -> {
                            Map<String, Object> map = new HashMap<>();
                            map.put("ct_id", k);
                            map.put("count", ((LongSummaryStatistics) v).getSum());
                            resultList.add(map);
                        }
                );
            }
        } catch (Exception e) {
            log.error("获取分类结果数量异常：", e);
        }
        return resultList;
    }


    private List getCountByCt(Map<String, String> mp) {

        long start = System.currentTimeMillis();
        List resultList = new ArrayList();
        try {
            String searchApiUrl = Config.getCommonKey(Config.solrMp, "searchapi.http.url");
            log.info("getCountByCt--searchApiUrl=" + searchApiUrl);
            log.info("getCountByCt--mp=" + mp.toString());
            String result = HttpClientUtil.doPost(searchApiUrl, mp);
            log.info("=========请求时间:{}毫秒========", System.currentTimeMillis() - start);
            log.info("getCountByCt--result" + result);
            String message = JSONObject.parseObject(result).getJSONObject("sitech").getJSONObject("body").getString("message");
            List<HashMap> list = JSONObject.parseArray(message, HashMap.class);
            HashMap<String, Integer> ctCount = new HashMap<>();


            long countBefore = System.currentTimeMillis();
            for (HashMap map : list) {
                String parent_path_id = (String) map.get("parent_path_id");
                String[] ctIdArr = parent_path_id.split("_");
                for (String s : ctIdArr) {
                    int count = ctCount.get(s) == null ? 1 : (ctCount.get(s) + 1);
                    ctCount.put(s, count);
                }
            }
            long countAfter = System.currentTimeMillis();

            log.info("=========>>>>>>>>>遍历时间:{}毫秒<<<<<<<<<<=========", countAfter - countBefore);

            for (String ct : ctCount.keySet()) {
                HashMap<String, String> p = new HashMap<>();
                p.put("ct_id", ct);
                int count = ctCount.get(ct) == null ? 0 : ctCount.get(ct);
                p.put("count", count + "");
                resultList.add(p);
            }

        } catch (Exception e) {
            log.error("获取分类结果数量异常：", e);
        }

        long end = System.currentTimeMillis();
        log.info("========总共耗时：{}毫秒=========", end - start);
        return resultList;
    }


    private List getCountByCt2(TestSi_Tech001JsonData jsonData) {
        long startTime = System.currentTimeMillis();

        jsonData.setReq_id(jsonData.getReq_id());
        jsonData.setService_code(Session.getUserInfo().getEp_id() + "A001");
        jsonData.setInterface_code("si_tech002");
        jsonData.setStart(0);
        jsonData.setRows(1);
        //分类分组查询
        jsonData.setFacet_field("parent_path_id");
        String res = SolrUtil.SolrPost(jsonData);
        long responseTime = System.currentTimeMillis();

        log.info("==========>>>>>>>>>>分组统计,请求时间{}毫秒，结果集:{}=========：{}", responseTime - startTime, res);
        String countByPath = JSONObject.parseObject(res).getJSONObject("sitech").getJSONObject("body").getString("message");
        List<HashMap> list = JSONObject.parseArray(countByPath, HashMap.class);

        HashMap<String, Integer> countMap = new HashMap<>();
        for (HashMap mp : list) {
            for (Object k : mp.keySet()) {
                Integer pathCount = Integer.parseInt(mp.get(k).toString());
                String[] parentPathId = k.toString().split("_");
                for (String ct : parentPathId) {
                    int count = countMap.get(ct) == null ? pathCount : (countMap.get(ct) + pathCount);
                    countMap.put(ct, count);
                }
            }
        }
        long countTime = System.currentTimeMillis();
        log.info("=========>>>>>>>>>>结果计算时间:{}毫秒<<<<<<<<<<==========", countTime - responseTime);

        List countList = new ArrayList();
        for (String ct : countMap.keySet()) {
            HashMap<String, String> p = new HashMap<>();
            p.put("ct_id", ct);
            int c3 = countMap.get(ct) == null ? 0 : countMap.get(ct);
            p.put("count", c3 + "");
            countList.add(p);
        }

        log.info("==========>>>>>>>>>> 总耗时：{}毫秒 <<<<<<<<<<==========", System.currentTimeMillis() - startTime);
        return countList;
    }

    private String getDateTitle(String docTitle, String end_time) {
        if (StringUtils.isEmpty(docTitle)) {
            return docTitle;
        }
        String title = docTitle.replace("[", "").replace("]", "");
        //湖北政企需求：知识标题后边增加预警信息(1个月到期-红色字体，3个月到期-橙色字体）
        String is_display_warning = Config.getKey(Config.kmsMp, "is_display_warning");
        AtomicInteger count3Mon = new AtomicInteger();
        AtomicInteger count1Mon = new AtomicInteger();
        if ("Y".equals(is_display_warning)) {
            Arrays.stream(end_time.split(",")).forEach(endTime -> {
                if (StringUtils.isNotEmpty(endTime)) {
                    try {
                        SimpleDateFormat sdf = new SimpleDateFormat("yyyy-MM-dd HH:mm:ss");
                        Date end_date = sdf.parse(endTime);
                        if (end_date != null) {
                            //处理时间差
                            long mon_1 = 30 * 86400 * 1000L;
                            long mon_3 = 30 * 86400 * 1000L * 3;
                            long endTimeL = end_date.getTime();
                            long nowTimeL = new Date().getTime();
                            long time = endTimeL - nowTimeL;
                            //小于等于三个月并且大于一个月  橙色
                            if (time <= mon_3 && time > mon_1) {
                                count3Mon.getAndIncrement();
                            }
                            //小于等于一个月  红色
                            if (time <= mon_1) {
                                count1Mon.getAndIncrement();
                            }
                        }
                    } catch (Exception e) {
                        log.error("证件到期提醒解析异常：", e);
                    }
                }
            });
        }
        if (count1Mon.get() > 0) {
            title += " <font color='red'>【一个月到期的有" + count1Mon.get() + "个】</font>";
        }
        if (count3Mon.get() > 0) {
            title += " <font color='orange'>【三个月到期的有" + count3Mon.get() + "个】</font>";
        }
        return title;
    }
}
